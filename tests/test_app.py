"""Kiểm thử end-to-end (chế độ offline nếu chưa có LLM_API_KEY). Chạy: python -m pytest -q"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LLM_API_KEY", "")

from starlette.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


def test_health():
    assert client.get("/health").status_code == 200


def test_ui_served():
    r = client.get("/")
    assert r.status_code == 200 and "COUNTER-SNARE" in r.text
    for path in ("/static/js/main.js", "/static/js/investigation.js", "/static/css/app.css"):
        assert client.get(path).status_code == 200


def test_false_positive_payroll_is_cleared_without_str():
    p3 = next(p for p in main.PRESETS if p["id"] == "P3")
    r = client.post("/api/investigate", json={"text": p3["text"]}).json()
    assert r["status"] == "CLEARED" and "str" not in r
    assert any(m["code"] == "G_PAYROLL" for m in r["clearance"]["accounts"][0]["mitigating"])


def test_shapley_attribution_is_additive_and_meaningful():
    mule = main.CAMPAIGNS[0]["collectors"][0]
    contrib = main.BANK.risk(mule)["contributions"]
    assert contrib and contrib[0]["method"] == "shapley_mc" and contrib[0]["impact"] > 0.1


def test_investigate_finds_whole_ring_and_blocks_injection():
    msg = main.MESSAGES[0]
    camp = next(c for c in main.CAMPAIGNS if c["plan"]["campaign_id"] == msg["campaign_id"])
    r = client.post("/api/investigate", json={"text": msg["text"]}).json()
    assert r["guard"]["injection"], "phải phát hiện prompt injection trong mẫu #1"
    found = {n["id"] for n in r["ring"]["nodes"] if n["role"] in ("collector", "layer", "cashout")}
    truth = set(camp["collectors"] + camp["layers"] + camp["cashouts"])
    assert truth <= found
    assert r["judge"]["deterministic_ok"]
    a1 = next(a for a in r["actions"] if a["tool"] == "delay_transactions")
    assert "DENY" in a1["agent_attempt"]


def test_invocations_entrypoint():
    r = client.post("/invocations", json={"message": main.MESSAGES[1]["text"]},
                    headers={"X-GreenNode-AgentBase-Session-Id": "s1", "X-GreenNode-AgentBase-User-Id": "u1"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success" and body["mules"]


def test_agent_cannot_take_legal_action_but_officer_can():
    r = client.post("/api/agent_try", json={"tool": "submit_str"}).json()
    assert r["effect"] == "DENY"
    case = client.post("/api/investigate", json={"text": main.MESSAGES[2]["text"]}).json()
    no_name = client.post("/api/approve", json={"case_id": case["case_id"], "action_id": "A1", "officer": ""})
    assert no_name.status_code == 400
    ok = client.post("/api/approve", json={"case_id": case["case_id"], "action_id": "A1", "officer": "Chuyên viên A"}).json()
    assert ok["ok"]
    freeze = client.post("/api/approve", json={"case_id": case["case_id"], "action_id": "A4", "officer": "Chuyên viên A"})
    assert freeze.status_code == 400  # phong tỏa cần quyết định cơ quan có thẩm quyền


def test_no_hallucinated_account():
    r = client.post("/api/investigate", json={"text": "Chuyển tiền gấp vào STK 123456789999 ngân hàng NHZ"}).json()
    assert r["status"] == "NO_SEED"


def test_triage_no_missed_mules():
    m = client.get("/api/triage").json()["metrics"]
    assert m["missed_mules"] == 0 and m["auto_closed"] > 0


def test_preset4_needs_honeypot_then_reveals_ring():
    p4 = next(p for p in main.PRESETS if p["id"] == "P4")
    r = client.post("/api/investigate", json={"text": p4["text"]}).json()
    assert r["status"] == "NO_SEED"  # chưa có số tài khoản -> Execute không có gì để điều tra
    h = client.post("/api/honeypot", json={"text": p4["text"], "campaign_id": p4["campaign_id"]}).json()
    assert h["transcript"][0]["text"] == p4["text"] and not h["opening_had_account"]
    hidden = next(m for m in main.MESSAGES if m["campaign_id"] == p4["campaign_id"])
    assert hidden["seed_account"] in h["extracted_accounts"]
    case = client.post("/api/investigate", json={"text": h["scam_text"]}).json()
    assert case["ring"]["summary"]["n_mules"] > 0


def test_honeypot_uses_typed_opening_and_matching_typology():
    opening = "Chào bạn, bên mình tuyển CTV làm nhiệm vụ like đơn hàng, hoa hồng 15% mỗi đơn, bạn tham gia không?"
    h = client.post("/api/honeypot", json={"text": opening}).json()
    assert h["transcript"][0]["text"] == opening
    assert h["typology"] == "viec_nhe_luong_cao" and h["extracted_accounts"]


def test_honeypot_extracts_account():
    r = client.post("/api/honeypot", json={"campaign_id": main.MESSAGES[0]["campaign_id"]}).json()
    assert main.MESSAGES[0]["seed_account"] in r["extracted_accounts"]
