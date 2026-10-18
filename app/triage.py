"""Phân loại cảnh báo (alert triage): hệ thống giám sát giao dịch theo LUẬT truyền thống sinh rất nhiều cảnh báo giả.
Agent tự đóng cảnh báo giả có lý do giải thích được, chỉ chuyển cho người các ca thật sự đáng ngờ hoặc chưa chắc chắn."""
from __future__ import annotations

import pandas as pd

from .bank import Bank, mask_name
from .model import reason_codes

RULES = {
    "TM-01": "≥ 8 người gửi khác nhau trong 24 giờ",
    "TM-02": "≥ 80% tiền vào được chuyển đi trong 60 phút, tổng vào ≥ 50 triệu",
    "TM-03": "Nhận khoản ≥ 100 triệu, gấp ≥ 10 lần thu nhập kê khai",
    "TM-04": "≥ 3 giao dịch 9–10 triệu (nghi chia nhỏ)",
    "TM-05": "Thiết bị dùng chung với chủ tài khoản khác",
}


def legacy_alerts(bank: Bank) -> pd.DataFrame:
    f = bank.feats[bank.feats["is_system"] == 0]
    acc = bank.acc
    max_single_in = bank.tx.groupby("dst")["amount"].max()
    rows = []
    for a, r in f.iterrows():
        hit = []
        if r["max_senders_24h"] >= 8:
            hit.append("TM-01")
        if r["fast_out_ratio"] >= 0.8 and r["sum_in"] >= 50_000_000:
            hit.append("TM-02")
        if max_single_in.get(a, 0) >= 100_000_000 and max_single_in.get(a, 0) >= 10 * max(acc.loc[a, "declared_income"], 1):
            hit.append("TM-03")
        if r["structuring_cnt"] >= 3:
            hit.append("TM-04")
        if r["shared_device_holders"] >= 1:
            hit.append("TM-05")
        if hit:
            rows.append({"alert_id": f"AL-{len(rows) + 1:04d}", "account_id": a, "rules": hit, "is_mule": int(r["is_mule"])})
    return pd.DataFrame(rows)


def triage(bank: Bank) -> dict:
    alerts = legacy_alerts(bank)
    out = []
    for _, al in alerts.iterrows():
        a = al["account_id"]
        f = bank.feats.loc[a]
        p = float(bank.p.get(a, 0.0))
        red, green = reason_codes(f)
        ato = f["foreign_device_out_ratio"] > 0 and f["account_age_days"] > 180
        if ato:
            decision, why = "CHUYỂN BẢO VỆ NẠN NHÂN", "Có giao dịch ra từ thiết bị lạ trên tài khoản lâu năm: nghi bị chiếm quyền, cần liên hệ khách hàng (không phải mule)"
        elif p >= 0.5:
            decision, why = "LEO THANG", "; ".join(r["text"] for r in red[:2]) or "Điểm rủi ro cao"
        elif p < 0.2:
            decision = "ĐÓNG (DƯƠNG TÍNH GIẢ)"
            why = "; ".join(g["text"] for g in green[:2]) or "Hành vi phù hợp hồ sơ khách hàng, điểm rủi ro thấp"
        else:
            decision, why = "NGƯỜI XEM XÉT", "Điểm rủi ro trung bình, cần chuyên viên đánh giá"
        acc = bank.acc.loc[a]
        out.append({"alert_id": al["alert_id"], "account_id": a, "holder": mask_name(acc["holder_name"]), "segment": acc["segment"],
                    "rules": [f"{r}: {RULES[r]}" for r in al["rules"]], "score": round(p, 3), "decision": decision, "reason": why,
                    "truth": "mule" if al["is_mule"] else "không phải mule"})
    df = pd.DataFrame(out)
    n = len(df)
    true_mules = int(alerts["is_mule"].sum()) if n else 0
    closed = df[df["decision"].str.startswith("ĐÓNG")] if n else df
    esc = df[df["decision"] == "LEO THANG"] if n else df
    missed = int((closed["truth"] == "mule").sum()) if n else 0
    metrics = {
        "alerts_total": n, "true_mule_alerts": true_mules, "false_alerts": n - true_mules,
        "legacy_false_positive_rate": round((n - true_mules) / n, 3) if n else 0,
        "auto_closed": int(len(closed)), "auto_closed_correct": int((closed["truth"] != "mule").sum()) if n else 0,
        "escalated": int(len(esc)), "escalated_true": int((esc["truth"] == "mule").sum()) if n else 0,
        "human_review": int((df["decision"] == "NGƯỜI XEM XÉT").sum()) if n else 0,
        "victim_protection": int((df["decision"] == "CHUYỂN BẢO VỆ NẠN NHÂN").sum()) if n else 0,
        "missed_mules": missed,
        "workload_reduction": round(len(closed) / n, 3) if n else 0,
        "analyst_minutes_saved": int(len(closed) * 25),
    }
    return {"metrics": metrics, "alerts": out, "rules": RULES}
