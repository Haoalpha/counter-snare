"""BẪY NGƯỢC – Agent săn đường dây tài khoản mule. Entry point chạy trên GreenNode AgentBase Runtime.

- POST /invocations : entrypoint chuẩn của AgentBase SDK (payload {"message": "<tin nhắn lừa đảo>"})
- GET  /health      : health check (AgentBase dùng để đánh dấu ACTIVE)
- GET  /            : giao diện web cho chuyên viên PCRT / giám khảo
- /api/*            : API cho giao diện
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

for _s in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252 làm SDK (rich) lỗi khi in tiếng Việt/ký hiệu
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv(Path(__file__).resolve().parent / ".env")

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from app.agents import TYPO_KEYWORDS, Investigator, _fold  # noqa: E402
from app.arena import run_arena  # noqa: E402
from app.audit import audit  # noqa: E402
from app.bank import Bank  # noqa: E402
from app.honeypot import run_honeypot  # noqa: E402
from app.llm import llm  # noqa: E402
from app.memory import ring_memory  # noqa: E402
from app.model import MuleModel, np_default  # noqa: E402
from app.policy import OFFICER, POLICY_GROUP, TOOL_DESCRIPTIONS, PolicyDenied, call_tool, evaluate  # noqa: E402
from app.simulator import TYPOLOGIES  # noqa: E402
from app.triage import triage  # noqa: E402

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC = ROOT / "static"

if not (DATA / "world.pkl").exists():
    from scripts.build_assets import main as build_assets
    build_assets()

_world = pickle.loads((DATA / "world.pkl").read_bytes())
MODEL = MuleModel.load(DATA / "model.pkl")
BANK = Bank(_world["accounts"], _world["transactions"], _world["features"], MODEL, _world["meta"])
CAMPAIGNS = _world["campaigns"]
MESSAGES = _world["scam_messages"]
# mock SIMO: một số tài khoản gom tiền đã bị ngân hàng khác báo lên hệ thống
SIMO = {c["collectors"][0] for c in CAMPAIGNS[1::2]}
EVAL = json.loads((DATA / "eval.json").read_text(encoding="utf-8"))
TRIAGE = triage(BANK)
INVESTIGATOR = Investigator(BANK, SIMO)
CASES: dict[str, dict] = {}
_lock = threading.Lock()
STARTED_AT = datetime.now().isoformat(timespec="seconds")


def _build_presets() -> list[dict]:
    """3 kịch bản demo: lừa đầu tư, rửa tiền đa tầng tốc độ cao (kèm prompt injection), và DƯƠNG TÍNH GIẢ (chi lương doanh nghiệp)."""
    by_typ = {m["typology"]: m for m in MESSAGES}
    presets = [
        {"id": "P1", "label": "Phishing Investment Scam", "expect": "Mule ring + STR",
         "text": by_typ.get("dau_tu_tien_ao", MESSAGES[0])["text"]},
        {"id": "P2", "label": "Fast Multi-hop Laundering", "expect": "Mule ring + prompt-injection attempt",
         "text": MESSAGES[0]["text"]},
    ]
    f = BANK.feats
    cand = f[(f["is_business"] == 1) & (f["payroll_out_ratio"] >= 0.7)].sort_values("uniq_receivers", ascending=False)
    cand = [a for a in cand.index if BANK.acc.loc[a, "bank"] == "NHX"]
    if cand:
        emp = cand[0]
        outs = BANK.tx.iloc[list(BANK.by_src.get(emp, []))]
        pay = outs[outs["memo"].str.lower().str.contains("luong", na=False)]
        day = pay["ts"].dt.date.value_counts().idxmax()
        d = pay[pay["ts"].dt.date == day]
        presets.append({"id": "P3", "label": "False Positive - Corporate Payroll", "expect": "Auto-dismiss with explanation",
                        "text": (f"[CẢNH BÁO TM-01 – hệ thống giám sát theo luật] Tài khoản {emp} ngân hàng NHX "
                                 f"({BANK.acc.loc[emp, 'holder_name']}) thực hiện {len(d)} lệnh chuyển tiền tới {d['dst'].nunique()} "
                                 f"người nhận khác nhau trong ngày {day.strftime('%d/%m/%Y')}, tổng "
                                 + f"{int(d['amount'].sum()):,}".replace(",", ".") + " đ. Đề nghị rà soát dấu hiệu phân tán tiền.")})
    # P4: kẻ gian mới chỉ tiếp cận, CHƯA lộ tài khoản nhận tiền -> Execute không có gì để điều tra, cần Honeypot Decoy
    hidden = next((m for m in MESSAGES[1:] if m["typology"] == "gia_danh_cong_an"), MESSAGES[1])
    presets.append({"id": "P4", "label": "Opening Contact - No Account Yet", "expect": "Use Honeypot Decoy Agent",
                    "campaign_id": hidden["campaign_id"], "honeypot": True,
                    "text": ("Alo, bác có phải chủ thuê bao này không ạ? Tôi là cán bộ điều tra Công an quận. Hồ sơ của bác đang liên quan "
                             "đến một đường dây rửa tiền xuyên quốc gia, bác phải hợp tác xác minh ngay trong hôm nay và tuyệt đối "
                             "không được nói với con cháu.")})
    return presets


PRESETS = _build_presets()

app = GreenNodeAgentBaseApp()


def J(data, status: int = 200) -> JSONResponse:
    return JSONResponse(json.loads(json.dumps(data, ensure_ascii=False, default=np_default)), status_code=status)


def _store(res: dict) -> dict:
    with _lock:
        CASES[res["case_id"]] = res
        if len(CASES) > 200:
            CASES.pop(next(iter(CASES)))
    return res


# ---------------- AgentBase SDK entrypoint ----------------
@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    text = payload.get("message") or payload.get("text") or payload.get("prompt") or ""
    if not text.strip():
        return {"status": "error", "error": "Gửi {\"message\": \"<nội dung tin nhắn lừa đảo>\"}"}
    res = _store(INVESTIGATOR.run(text, payload.get("seeds")))
    if "ring" not in res:
        return {"status": "no_seed", "case_id": res["case_id"], "intel": res["intel"],
                "response": "Không tìm thấy số tài khoản thuộc ngân hàng trong tin nhắn."}
    if res["status"] == "CLEARED":
        return {"status": "cleared", "case_id": res["case_id"], "clearance": res["clearance"],
                "response": "Không phát hiện đường dây mule – đề xuất đóng cảnh báo (dương tính giả) kèm lý do giải thích.",
                "ui": f"/?case={res['case_id']}"}
    s = res["ring"]["summary"]
    return {
        "status": "success", "case_id": res["case_id"],
        "response": (f"Đã khoanh vùng đường dây {res['intel']['typology_label']}: {s['n_mules']} tài khoản nghi mule, "
                     f"{s['n_victims']} nạn nhân, thiệt hại {res['str']['total_victim_loss']}, ước còn {res['str']['est_remaining']} "
                     f"trong đường dây. Dự thảo STR đã sẵn sàng, chờ chuyên viên PCRT duyệt (agent bị Policy chặn tự trì hoãn giao dịch)."),
        "mules": [n["id"] for n in res["ring"]["nodes"] if n["role"] in ("collector", "layer", "cashout")],
        "judge_passed": res["judge"]["passed"], "actions": res["actions"], "ui": f"/?case={res['case_id']}",
        "session_id": context.session_id if context else None,
    }


@app.ping
def health() -> PingStatus:
    return PingStatus.HEALTHY


# ---------------- UI + API ----------------
async def index(request: Request):
    return FileResponse(STATIC / "index.html")


async def meta(request: Request):
    s = BANK.acc
    return J({
        "llm_enabled": llm.enabled, "llm_models": llm.models, "memory_backend": ring_memory.backend,
        "world": {"accounts": int((s["segment"] != "HE_THONG").sum()), "transactions": int(len(BANK.tx)),
                  "start": _world["meta"]["start"], "days": _world["meta"]["days"], "campaigns": len(CAMPAIGNS)},
        "samples": [{"campaign_id": m["campaign_id"], "typology": m["typology"], "label": TYPOLOGIES[m["typology"]],
                     "text": m["text"]} for m in MESSAGES],
        "policy_group": POLICY_GROUP, "tools": TOOL_DESCRIPTIONS, "presets": PRESETS,
        "runtime": {"platform": "GreenNode AgentBase Runtime" if os.environ.get("GREENNODE_ENDPOINT_URL") else "local",
                    "endpoint": os.environ.get("GREENNODE_ENDPOINT_URL", ""), "port": 8080,
                    "agent_identity": bool(os.environ.get("GREENNODE_AGENT_IDENTITY")),
                    "memory_id": os.environ.get("MEMORY_ID", ""), "started_at": STARTED_AT,
                    "cases_processed": len(CASES), "model_version": "v2 (Red Arena hardened)"},
        "eval_headline": {"triage": EVAL.get("triage"), "account_level": EVAL.get("account_level")},
    })


def investigate(request_json: dict):
    text = request_json.get("text", "")
    if not text.strip():
        return J({"error": "Thiếu nội dung tin nhắn"}, 400)
    return J(_store(INVESTIGATOR.run(text, request_json.get("seeds"))))


async def api_investigate(request: Request):
    body = await request.json()
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(investigate, body)


async def api_case(request: Request):
    c = CASES.get(request.path_params["case_id"])
    return J(c) if c else J({"error": "Không tìm thấy vụ việc"}, 404)


def _pick_scenario(text: str, campaign_id: str | None) -> dict:
    """Kịch bản ẩn của đường dây mà ScamBot (mô phỏng) sẽ dùng: theo preset nếu có, nếu không thì theo thủ đoạn
    nhận diện từ câu mở đầu (ưu tiên kịch bản không chứa đòn prompt injection)."""
    if campaign_id:
        m = next((m for m in MESSAGES if m["campaign_id"] == campaign_id), None)
        if m:
            return m
    low = _fold(text or "")
    scores = {t: sum(_fold(k) in low for k in kws) for t, kws in TYPO_KEYWORDS.items()}
    best = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else None
    pool = [m for m in MESSAGES[1:] if m["typology"] == best] or [m for m in MESSAGES if m["typology"] == best] or MESSAGES[1:]
    return pool[0]


async def api_honeypot(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    msg = _pick_scenario(text, body.get("campaign_id"))
    from starlette.concurrency import run_in_threadpool
    return J(await run_in_threadpool(run_honeypot, msg, text or None))


async def api_agent_try(request: Request):
    body = await request.json()
    tool = body.get("tool", "delay_transactions")
    try:
        call_tool("agent:bay-nguoc", tool, lambda: None, case_id=body.get("case_id", ""))
        return J({"tool": tool, "effect": "ALLOW"})
    except PolicyDenied as e:
        effect, st = evaluate("agent:bay-nguoc", tool)
        return J({"tool": tool, "effect": "DENY", "message": str(e), "matched_statement": st})


async def api_approve(request: Request):
    body = await request.json()
    case = CASES.get(body.get("case_id", ""))
    if not case:
        return J({"error": "Không tìm thấy vụ việc"}, 404)
    officer = (body.get("officer") or "").strip()
    if not officer:
        return J({"error": "Cần tên chuyên viên PCRT phê duyệt"}, 400)
    act = next((a for a in case.get("actions", []) if a["id"] == body.get("action_id")), None)
    if not act:
        return J({"error": "Không tìm thấy hành động"}, 404)
    tool = act["tool"]
    if tool == "freeze_account" and not (body.get("authority_decision") or "").strip():
        return J({"error": "Phong tỏa chỉ thực hiện khi có số quyết định của cơ quan có thẩm quyền (Điều 45)"}, 400)
    try:
        call_tool(OFFICER, tool, lambda: None, case_id=case["case_id"])
    except PolicyDenied as e:
        return J({"error": str(e)}, 403)
    act["status"] = f"ĐÃ DUYỆT bởi {officer}" + (" – đã nộp NHNN (mô phỏng)" if tool == "submit_str" else "")
    if tool == "freeze_account":
        act["status"] += f" theo QĐ {body['authority_decision']}"
    audit.log("human_approval", case_id=case["case_id"], officer=officer, tool=tool, action_id=act["id"])
    return J({"ok": True, "action": act})


async def api_triage(request: Request):
    return J(TRIAGE)


async def api_arena(request: Request):
    body = await request.json()
    diff = body.get("difficulty", "vua")
    if diff not in ("de", "vua", "kho"):
        diff = "vua"
    from starlette.concurrency import run_in_threadpool
    res = await run_in_threadpool(run_arena, MODEL, diff, None, bool(body.get("use_llm", True)))
    return J(res)


async def api_llm_status(request: Request):
    return J({"enabled": llm.enabled, "rate_limits": llm.limiter.snapshot(), "routes": __import__("app.llm", fromlist=["ROUTES"]).ROUTES})


async def api_eval(request: Request):
    return J(EVAL)


async def api_audit(request: Request):
    return J({"events": audit.list(request.query_params.get("case_id"), limit=int(request.query_params.get("limit", 300)))})


async def api_account(request: Request):
    a = request.path_params["account_id"]
    if not BANK.exists(a):
        return J({"error": "Không có tài khoản"}, 404)
    tx = BANK.transactions(a, 40)
    return J({"profile": BANK.profile(a, masked=True), "risk": BANK.risk(a),
              "transactions": [{**r, "ts": str(r["ts"])} for r in tx.to_dict("records")]})


app.router.routes.extend([
    Route("/", index, methods=["GET"]),
    Mount("/static", app=StaticFiles(directory=str(STATIC)), name="static"),
    Route("/api/meta", meta, methods=["GET"]),
    Route("/api/investigate", api_investigate, methods=["POST"]),
    Route("/api/case/{case_id}", api_case, methods=["GET"]),
    Route("/api/honeypot", api_honeypot, methods=["POST"]),
    Route("/api/agent_try", api_agent_try, methods=["POST"]),
    Route("/api/approve", api_approve, methods=["POST"]),
    Route("/api/triage", api_triage, methods=["GET"]),
    Route("/api/arena", api_arena, methods=["POST"]),
    Route("/api/eval", api_eval, methods=["GET"]),
    Route("/api/llm_status", api_llm_status, methods=["GET"]),
    Route("/api/audit", api_audit, methods=["GET"]),
    Route("/api/account/{account_id}", api_account, methods=["GET"]),
])

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8080")), host=os.environ.get("HOST", "0.0.0.0"))
