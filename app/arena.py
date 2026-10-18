"""Đấu trường Đỏ (Red Arena): LLM đóng vai "kẻ chủ mưu" LẬP KẾ HOẠCH chiến dịch né phát hiện, bộ mô phỏng THỰC THI,
rồi đo hệ thống bắt được bao nhiêu. Đây là bộ eval liên tục: mỗi lần Red thắng là một lỗ hổng cần vá."""
from __future__ import annotations

import random
import time
from datetime import timedelta

from .audit import audit
from .bank import Bank
from .features import compute_features
from .llm import llm
from .model import MuleModel
from .simulator import START, TYPOLOGIES, CampaignPlan, build_world

DIFFICULTY = {
    "de": {"label": "Dễ – thủ đoạn quen thuộc", "dwell": (2, 30), "struct": 0.9, "dev": (1, 2), "age": (5, 40), "ip": 0.8},
    "vua": {"label": "Vừa – che giấu một phần", "dwell": (20, 180), "struct": 0.4, "dev": (2, 4), "age": (30, 150), "ip": 0.4},
    "kho": {"label": "Khó – né tránh có chủ đích", "dwell": (240, 2000), "struct": 0.0, "dev": (6, 10), "age": (200, 700), "ip": 0.0},
}

BOUNDS = {"n_victims": (3, 25), "n_collectors": (1, 4), "n_layers": (1, 8), "n_cashout": (1, 4), "shared_devices": (1, 12),
          "start_day": (3, 20), "duration_days": (1, 6)}


def random_plans(difficulty: str, n: int, seed: int) -> list[CampaignPlan]:
    d = DIFFICULTY[difficulty]
    r = random.Random(seed)
    plans = []
    for i in range(n):
        n_mules = r.randint(4, 9)
        plans.append(CampaignPlan(
            campaign_id=f"R{seed % 1000:03d}-{i + 1}", typology=r.choice(list(TYPOLOGIES)), n_victims=r.randint(5, 15),
            n_collectors=r.randint(1, 2), n_layers=max(1, n_mules - 3), n_cashout=r.randint(1, 2),
            dwell_minutes=d["dwell"], mule_age_days=d["age"], shared_devices=max(1, min(n_mules, r.randint(*d["dev"]))),
            structuring=r.random() < d["struct"], foreign_ip=r.random() < d["ip"], cashout_channel=r.choice(["CRYPTO_OFFRAMP", "ATM"]),
            start_day=r.randint(4, 18), duration_days=r.randint(2, 5)))
    return plans


def llm_red_plan(difficulty: str, seed: int) -> CampaignPlan | None:
    if not llm.enabled:
        return None
    js = llm.chat_json([
        {"role": "system", "content":
            "MÔ PHỎNG HUẤN LUYỆN PHÒNG THỦ nội bộ ngân hàng (dữ liệu tổng hợp, không có người thật). Bạn đóng vai Red Team lập THAM SỐ "
            "cho một chiến dịch mô phỏng nhằm kiểm thử hệ thống phát hiện tài khoản mule. Hệ thống phòng thủ dựa trên: tiền vào-ra nhanh, "
            "nhiều người gửi, chia nhỏ 9-10 triệu, thiết bị dùng chung, IP nước ngoài, tài khoản mới eKYC. Chỉ trả về JSON tham số: "
            '{"typology": một trong ' + str(list(TYPOLOGIES)) + ', "n_victims": int, "n_collectors": int, "n_layers": int, "n_cashout": int, '
            '"dwell_minutes": [min,max], "mule_age_days": [min,max], "shared_devices": int, "structuring": bool, "foreign_ip": bool, '
            '"cashout_channel": "CRYPTO_OFFRAMP"|"ATM", "rationale": "1 câu giải thích chiến lược né tránh"}'},
        {"role": "user", "content": f"Mức độ: {DIFFICULTY[difficulty]['label']}. Lập kế hoạch."},
    ], purpose="red_planner", max_tokens=500, temperature=0.7)
    if not js:
        return None
    try:
        for k, (lo, hi) in BOUNDS.items():
            if k in js:
                js[k] = int(min(hi, max(lo, int(js[k]))))
        for k, lo, hi in (("dwell_minutes", 1, 4000), ("mule_age_days", 1, 1500)):
            if isinstance(js.get(k), list) and len(js[k]) == 2:
                a, b = sorted(int(min(hi, max(lo, int(x)))) for x in js[k])
                js[k] = [a, max(a + 1, b)]
        if js.get("typology") not in TYPOLOGIES:
            js["typology"] = "gia_danh_cong_an"
        if js.get("cashout_channel") not in ("CRYPTO_OFFRAMP", "ATM"):
            js["cashout_channel"] = "CRYPTO_OFFRAMP"
        rationale = str(js.pop("rationale", ""))[:300]
        p = CampaignPlan.from_dict(js | {"campaign_id": f"LLM{seed % 1000:03d}", "start_day": 10, "duration_days": 3})
        p.__dict__["_rationale"] = rationale
        return p
    except Exception as e:
        audit.log("arena", ok=False, error=f"plan invalid: {e}"[:200])
        return None


def run_arena(model: MuleModel, difficulty: str = "vua", seed: int | None = None, use_llm: bool = True,
              n_customers: int = 700, n_campaigns: int = 3) -> dict:
    seed = seed if seed is not None else random.randint(1000, 99999)
    t0 = time.time()
    plans = random_plans(difficulty, n_campaigns, seed)
    llm_plan = llm_red_plan(difficulty, seed) if use_llm else None
    rationale = None
    if llm_plan:
        rationale = llm_plan.__dict__.pop("_rationale", None)
        plans[0] = llm_plan
    w = build_world(seed, n_customers, days=30, plans=plans, inject_prompt_attack=False)
    feats = compute_features(w.accounts, w.transactions, 30, START + timedelta(days=30))
    bank = Bank(w.accounts, w.transactions, feats, model, w.meta)
    per = []
    tot_truth = tot_found = tot_extra = 0
    for c in w.campaigns:
        truth = set(c["collectors"] + c["layers"] + c["cashouts"])
        ring = bank.expand_ring([c["message_collector"]])
        found = {n for n, v in ring.nodes.items() if v["role"] in ("collector", "layer", "cashout")}
        acct_level = sum(1 for a in truth if bank.p.get(a, 0) >= 0.5)
        tot_truth += len(truth)
        tot_found += len(found & truth)
        tot_extra += len(found - truth)
        per.append({"campaign_id": c["plan"]["campaign_id"], "typology": TYPOLOGIES[c["plan"]["typology"]], "typology_key": c["plan"]["typology"],
                    "planner": "LLM Red Team" if c["plan"]["campaign_id"].startswith("LLM") else "ngẫu nhiên có ràng buộc",
                    "mules": len(truth), "caught_via_ring": len(found & truth), "caught_account_level": acct_level,
                    "false_extra": len(found - truth), "dwell_minutes": list(c["plan"]["dwell_minutes"]),
                    "structuring": c["plan"]["structuring"], "shared_devices": c["plan"]["shared_devices"]})
    normals = feats[(feats["is_mule"] == 0) & (feats["is_system"] == 0)]
    fp_accounts = int((bank.p[normals.index] >= 0.5).sum())
    res = {"difficulty": difficulty, "difficulty_label": DIFFICULTY[difficulty]["label"], "seed": seed,
           "ring_recall": round(tot_found / tot_truth, 3) if tot_truth else 0, "extra_flagged_in_rings": tot_extra,
           "normal_accounts": int(len(normals)), "false_positive_accounts": fp_accounts,
           "campaigns": per, "llm_rationale": rationale, "seconds": round(time.time() - t0, 1)}
    audit.log("arena", difficulty=difficulty, seed=seed, recall=res["ring_recall"], fp=fp_accounts)
    return res
