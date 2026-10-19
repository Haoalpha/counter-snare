"""Orchestrator tự chủ cho Trung tâm Tác chiến An ninh Tài chính (Ops Center).

Người dùng chỉ đưa một mối đe dọa vào (hoặc bật Autopilot) – Orchestrator TỰ quyết định cử agent nào, theo thứ tự nào:
  - có tài khoản nhận tiền thuộc ngân hàng  -> đội điều tra (LangGraph) khoanh vùng đường dây + dự thảo STR
  - chưa lộ tài khoản                       -> TỰ cử Decoy Agent (mô phỏng) để kẻ gian lộ tài khoản, rồi quay lại điều tra
  - tài khoản ở ngân hàng khác              -> chuyển SIMO / đề nghị liên ngân hàng
  - không có đường dây quanh hạt giống      -> đóng cảnh báo dương tính giả, có giải thích
Mọi bước được phát lên event bus (Agentic Thought Stream); hành động pháp lý vẫn dừng ở cổng phê duyệt của con người.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from .audit import audit
from .bank import vnd
from .events import emit, subscribe, unsubscribe
from .honeypot import run_honeypot

ORCH = "Orchestrator"
DECOY = "Decoy Agent"
MAX_EVENTS = 600


class RunStore:
    """Lưu sự kiện từng lượt chạy để giao diện polling (GET events?after=N)."""

    def __init__(self, cap: int = 120):
        self.cap = cap
        self.runs: OrderedDict[str, dict] = OrderedDict()
        self.lock = threading.Lock()

    def create(self, case_id: str, meta: dict) -> dict:
        run = {"case_id": case_id, "events": [], "done": False, "result": None, "meta": meta, "created": time.time()}
        with self.lock:
            self.runs[case_id] = run
            while len(self.runs) > self.cap:
                old, _ = self.runs.popitem(last=False)
                unsubscribe(old)
        subscribe(case_id, lambda ev: self.append(case_id, ev))
        return run

    def append(self, case_id: str, ev: dict) -> None:
        with self.lock:
            run = self.runs.get(case_id)
            if not run or len(run["events"]) >= MAX_EVENTS:
                return
            ev = dict(ev, seq=len(run["events"]))
            run["events"].append(ev)

    def finish(self, case_id: str, result: dict) -> None:
        with self.lock:
            run = self.runs.get(case_id)
            if run:
                run["result"], run["done"] = result, True

    def get(self, case_id: str, after: int = 0) -> dict | None:
        with self.lock:
            run = self.runs.get(case_id)
            if not run:
                return None
            evs = run["events"][after:]
            return {"case_id": case_id, "events": evs, "next": after + len(evs), "done": run["done"], "meta": run["meta"],
                    "result": run["result"] if run["done"] else None}

    def list(self) -> list[dict]:
        with self.lock:
            out = []
            for r in reversed(self.runs.values()):
                res = r["result"] or {}
                out.append({"case_id": r["case_id"], "meta": r["meta"], "done": r["done"], "status": res.get("status", "RUNNING"),
                            "created": r["created"]})
            return out


RUNS = RunStore()
_slots = threading.Semaphore(2)  # tối đa 2 vụ chạy song song để giữ hạn mức RPM của MaaS


def _say(cid: str, text: str, level: str = "info", agent: str = ORCH) -> None:
    emit(cid, type="thought", agent=agent, level=level, text=text)


def run_autonomous(investigator, case_id: str, text: str, meta: dict, pick_scenario) -> dict:
    src = meta.get("channel_label") or meta.get("source") or "analyst"
    t0 = time.time()
    if not _slots.acquire(blocking=False):
        _say(case_id, "Two investigations are already running — queued to respect the MaaS per-model RPM budget.", "warn")
        _slots.acquire()
    try:
        emit(case_id, type="node", agent=ORCH, node="orchestrate", status="start")
        _say(case_id, f"New threat from {src} ({len(text)} chars). I'll screen it, extract intelligence and pick the response "
                      "playbook myself; legal actions will stop at the human approval gate.")
        res = investigator.run(text, case_id=case_id)
        hp = None
        if res["status"] == "NO_SEED":
            intel = res.get("intel") or {}
            if intel.get("accounts_unknown"):
                _say(case_id, f"Receiving account {', '.join(intel['accounts_unknown'])} is held at another bank. Playbook: share it with "
                              "SIMO and send an interbank alert; nothing to delay on our ledger.", "warn")
                res["playbook"] = "interbank_referral"
            else:
                _say(case_id, "No receiving account exposed yet, so there is nothing to trace. Decision: dispatch the Decoy Agent "
                              "(“Bà Tư”, 68-year-old persona, simulation only) to keep the scammer talking until a mule account is revealed.")
                emit(case_id, type="node", agent=DECOY, node="honeypot", status="start")
                td = time.time()
                scen = pick_scenario(text, meta.get("campaign_id"))
                hp = run_honeypot(scen, text, case_id=case_id,
                                  on_turn=lambda t: emit(case_id, type="decoy", who=t["who"], text=t["text"]))
                emit(case_id, type="node", agent=DECOY, node="honeypot", status="done", ms=int((time.time() - td) * 1000))
                if hp["extracted_accounts"]:
                    _say(case_id, f"Decoy extracted receiving account {', '.join(hp['extracted_accounts'])} after "
                                  f"{len(hp['transcript'])} turns ({hp['mode']}). Re-entering the investigation loop with the new seed.", "ok")
                    res = investigator.run(hp["scam_text"], case_id=case_id)
                    res["playbook"] = "decoy_then_investigate"
                else:
                    _say(case_id, "Decoy could not extract an account. Case parked for analyst follow-up.", "warn")
                    res["playbook"] = "decoy_no_result"
                res["honeypot"] = hp
        elif res["status"] == "CLEARED":
            res["playbook"] = "false_positive_closure"
        else:
            res["playbook"] = "investigate"
        res["source"] = meta
        res["total_ms"] = int((time.time() - t0) * 1000)
        _say(case_id, _final_summary(res), "ok" if res["status"] in ("PENDING_APPROVAL", "CLEARED") else "info")
        emit(case_id, type="node", agent=ORCH, node="orchestrate", status="done", ms=res["total_ms"])
        audit.log("ops_run", case_id=case_id, status=res["status"], playbook=res.get("playbook"), ms=res["total_ms"])
        return res
    finally:
        _slots.release()


def _final_summary(res: dict) -> str:
    secs = res["total_ms"] / 1000
    if res["status"] == "CLEARED":
        return f"Done in {secs:.1f}s — false positive closed with an explanation. No STR, no customer friction."
    if res["status"] == "PENDING_APPROVAL":
        s = res["ring"]["summary"]
        j = res.get("judge") or {}
        return (f"Done in {secs:.1f}s — {s['n_mules']} mule accounts, {s['n_victims']} victims, {vnd(s['victim_loss'])} traced. "
                f"STR draft {'verified by Judge' if j.get('passed') else 'repaired by Judge'}; {len(res.get('actions', []))} actions "
                "are waiting for your approval below.")
    return f"Done in {secs:.1f}s — no actionable account on our ledger."
