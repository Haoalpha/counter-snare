"""Sinh toàn bộ tài sản dữ liệu (chạy lúc build Docker image, tất định theo seed):

1. 3 "thế giới" huấn luyện (thủ đoạn: giả danh công an, việc nhẹ lương cao, đầu tư tiền ảo)
2. Huấn luyện mô hình mule
3. 1 "thế giới" demo HOÀN TOÀN MỚI (seed khác + thủ đoạn chưa từng thấy: chiếm quyền điện thoại)
4. Đánh giá: demo world, triage, Red Arena 3 mức độ x 3 seed -> data/eval.json

Chạy: python -m scripts.build_assets
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.arena import random_plans, run_arena  # noqa: E402
from app.bank import Bank  # noqa: E402
from app.features import compute_features  # noqa: E402
from app.model import MuleModel, np_default  # noqa: E402
from app.simulator import START, build_world, default_plans  # noqa: E402
from app.triage import triage  # noqa: E402

DATA = ROOT / "data"
TRAIN_SEEDS = (7, 11, 13)
TRAIN_TYPOLOGIES = ["gia_danh_cong_an", "viec_nhe_luong_cao", "dau_tu_tien_ao"]
DEMO_SEED = 42
HARDEN_SEEDS = (501, 502, 503, 504, 505, 506)
EVAL_ARENA_SEEDS = (101, 202, 303, 404, 606)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    t0 = time.time()
    feats = []
    for s in TRAIN_SEEDS:
        w = build_world(s, 1500, plans=default_plans(s, TRAIN_TYPOLOGIES, 6, f"T{s}-"))
        feats.append(compute_features(w.accounts, w.transactions, 30, START + timedelta(days=30)))
        print(f"train world {s}: {len(w.accounts)} accounts, {len(w.transactions)} tx", flush=True)
    model_v1 = MuleModel().fit(pd.concat(feats))

    # Vòng tự tiến hóa: Red Arena sinh chiến dịch né tránh (seed riêng, KHÔNG trùng seed đánh giá) -> bổ sung vào huấn luyện
    hard_feats = []
    for s in HARDEN_SEEDS:
        for diff in ("vua", "kho"):
            w = build_world(s + (0 if diff == "vua" else 50), 700, plans=random_plans(diff, 3, s), inject_prompt_attack=False)
            hard_feats.append(compute_features(w.accounts, w.transactions, 30, START + timedelta(days=30)))
    model = MuleModel().fit(pd.concat(feats + hard_feats))
    model.save(DATA / "model.pkl")
    model_v1.save(DATA / "model_v1.pkl")
    print("trained v1 (baseline) + v2 (hardened by Red Arena)", flush=True)

    demo = build_world(DEMO_SEED, 2000)
    fdemo = compute_features(demo.accounts, demo.transactions, 30, START + timedelta(days=30))
    (DATA / "world.pkl").write_bytes(pickle.dumps({"accounts": demo.accounts, "transactions": demo.transactions,
                                                    "campaigns": demo.campaigns, "scam_messages": demo.scam_messages,
                                                    "meta": demo.meta, "features": fdemo}))
    print(f"demo world: {len(demo.accounts)} accounts, {len(demo.transactions)} tx", flush=True)

    bank = Bank(demo.accounts, demo.transactions, fdemo, model, demo.meta)
    d = fdemo[fdemo["is_system"] == 0]
    p = bank.p[d.index]
    y = d["is_mule"]
    yhat = (p >= 0.5).astype(int)
    ring_rows = []
    for c in demo.campaigns:
        truth = set(c["collectors"] + c["layers"] + c["cashouts"])
        ring = bank.expand_ring([c["message_collector"]])
        found = {n for n, v in ring.nodes.items() if v["role"] in ("collector", "layer", "cashout")}
        victims = set(c["victims"])
        fv = {n for n, v in ring.nodes.items() if v["role"].startswith("victim")}
        ring_rows.append({"campaign_id": c["plan"]["campaign_id"], "typology": c["plan"]["typology"],
                          "seen_in_training": c["plan"]["typology"] in TRAIN_TYPOLOGIES,
                          "mules": len(truth), "found": len(found & truth), "extra": len(found - truth),
                          "victims": len(victims), "victims_found": len(fv & victims)})
    tri = triage(bank)
    arena = {}
    for diff in ("de", "vua", "kho"):
        arena[diff] = {}
        for tag, m in (("v1", model_v1), ("v2", model)):
            runs = [run_arena(m, diff, seed=s, use_llm=False) for s in EVAL_ARENA_SEEDS]
            arena[diff][tag] = {"label": runs[0]["difficulty_label"],
                                "ring_recall_mean": round(sum(r["ring_recall"] for r in runs) / len(runs), 3),
                                "fp_accounts_mean": round(sum(r["false_positive_accounts"] for r in runs) / len(runs), 1),
                                "normal_accounts": runs[0]["normal_accounts"], "runs": runs}
            print(f"arena {diff} {tag}: recall {arena[diff][tag]['ring_recall_mean']} fp {arena[diff][tag]['fp_accounts_mean']}", flush=True)
    b1 = Bank(demo.accounts, demo.transactions, fdemo, model_v1, demo.meta)
    v1_demo_fp = int(((b1.p[d.index] >= 0.5) & (y == 0)).sum())

    ev = {
        "built_seconds": round(time.time() - t0, 1),
        "protocol": "v1: huấn luyện trên 3 thế giới tổng hợp (seed 7/11/13, 3 thủ đoạn). v2: bổ sung chiến dịch né tránh do Red Arena sinh "
                    f"(seed {HARDEN_SEEDS}). Đánh giá trên thế giới demo seed 42 chưa từng thấy (có thủ đoạn mới 'chiếm quyền điện thoại' "
                    f"không có trong huấn luyện) và Red Arena 3 mức độ x seed {EVAL_ARENA_SEEDS} (không trùng seed huấn luyện).",
        "demo_false_positives": {"v1": v1_demo_fp, "v2": int(((p >= 0.5) & (y == 0)).sum())},
        "account_level": {"auc_roc": round(roc_auc_score(y, p), 4), "avg_precision": round(average_precision_score(y, p), 4),
                          "precision@0.5": round(precision_score(y, yhat), 4), "recall@0.5": round(recall_score(y, yhat), 4),
                          "n_accounts": int(len(d)), "n_mules": int(y.sum())},
        "ring_level": ring_rows,
        "triage": tri["metrics"],
        "arena": arena,
    }
    (DATA / "eval.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2, default=np_default), encoding="utf-8")
    print(json.dumps({k: v for k, v in ev.items() if k != "arena"}, ensure_ascii=False, indent=1, default=np_default)[:3000])
    print("done in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
