"""Đặc trưng hành vi theo tài khoản. Mỗi đặc trưng ánh xạ tới một dấu hiệu đáng ngờ trong
Luật Phòng, chống rửa tiền 2022 (Điều 27, 28) để giải thích được cho chuyên viên."""
from __future__ import annotations

import numpy as np
import pandas as pd

SYSTEM_SEGMENTS = {"HE_THONG"}
BUSINESS_SEGMENTS = {"HO_KINH_DOANH", "DOANH_NGHIEP"}

FEATURES = [
    "n_in", "n_out", "log_sum_in", "uniq_senders", "uniq_receivers", "max_senders_24h",
    "fast_out_ratio", "median_dwell_min", "pass_through", "structuring_cnt", "income_ratio",
    "shared_device_holders", "foreign_ip_ratio", "night_ratio", "cashout_ratio", "account_age_days",
    "ekyc", "is_business", "same_holder_out_ratio", "small_in_ratio", "qr_in_ratio",
]

FEATURE_LABELS = {
    "fast_out_ratio": "Tỷ lệ tiền chuyển đi trong 60 phút sau khi nhận",
    "max_senders_24h": "Số người gửi khác nhau tối đa trong 24 giờ",
    "structuring_cnt": "Số giao dịch 9–10 triệu (chia nhỏ né ngưỡng sinh trắc học)",
    "income_ratio": "Dòng tiền vào / thu nhập kê khai",
    "shared_device_holders": "Số chủ tài khoản khác dùng chung thiết bị",
    "foreign_ip_ratio": "Tỷ lệ giao dịch từ IP nước ngoài",
    "night_ratio": "Tỷ lệ giao dịch 0h–5h",
    "cashout_ratio": "Tỷ lệ tiền ra tới sàn tài sản số/ATM",
    "account_age_days": "Tuổi tài khoản (ngày)",
    "pass_through": "Tỷ lệ tiền ra / tiền vào",
    "median_dwell_min": "Thời gian giữ tiền trung vị (phút)",
    "uniq_senders": "Số người gửi khác nhau",
    "uniq_receivers": "Số người nhận khác nhau",
    "is_business": "Là hộ kinh doanh/doanh nghiệp",
    "same_holder_out_ratio": "Tỷ lệ tiền ra sang tài khoản cùng chủ",
    "small_in_ratio": "Tỷ lệ giao dịch vào < 1 triệu",
    "qr_in_ratio": "Tỷ lệ giao dịch vào qua QR",
    "ekyc": "Mở tài khoản qua eKYC",
    "n_in": "Số giao dịch vào",
    "n_out": "Số giao dịch ra",
    "log_sum_in": "Tổng tiền vào (log)",
}


def compute_features(accounts: pd.DataFrame, tx: pd.DataFrame, days: int, as_of) -> pd.DataFrame:
    acc = accounts.set_index("account_id")
    sys_ids = set(acc.index[acc["segment"].isin(SYSTEM_SEGMENTS)])
    tx = tx.copy()
    tx["hour"] = tx["ts"].dt.hour
    tx["day"] = tx["ts"].dt.floor("D")

    inc = tx.groupby("dst")
    out = tx.groupby("src")
    f = pd.DataFrame(index=acc.index)
    f["n_in"] = inc.size()
    f["n_out"] = out.size()
    f["sum_in"] = inc["amount"].sum()
    f["sum_out"] = out["amount"].sum()
    f["uniq_senders"] = inc["src"].nunique()
    f["uniq_receivers"] = out["dst"].nunique()
    f["max_senders_24h"] = tx.groupby(["dst", "day"])["src"].nunique().groupby(level=0).max()
    f = f.fillna(0)
    f["log_sum_in"] = np.log1p(f["sum_in"])

    # tiền vào -> ra nhanh: với mỗi giao dịch ra, khoảng cách tới giao dịch vào gần nhất trước đó
    ins = tx[["dst", "ts"]].rename(columns={"dst": "acct", "ts": "in_ts"}).sort_values("in_ts")
    outs = tx[["src", "ts", "amount"]].rename(columns={"src": "acct", "ts": "out_ts"}).sort_values("out_ts")
    m = pd.merge_asof(outs, ins, left_on="out_ts", right_on="in_ts", by="acct", direction="backward")
    m["gap_min"] = (m["out_ts"] - m["in_ts"]).dt.total_seconds() / 60.0
    m["fast"] = (m["gap_min"] <= 60).astype(float)
    g = m.groupby("acct")
    fast_amt = (m["amount"] * m["fast"]).groupby(m["acct"]).sum()
    f["fast_out_ratio"] = (fast_amt / f["sum_out"].replace(0, np.nan)).fillna(0).clip(0, 1)
    f["median_dwell_min"] = g["gap_min"].median().reindex(f.index).fillna(10_000).clip(upper=10_000)

    f["pass_through"] = (np.minimum(f["sum_out"], f["sum_in"]) / f["sum_in"].replace(0, np.nan)).fillna(0)
    struct = tx[(tx["amount"] >= 9_000_000) & (tx["amount"] < 10_000_000)]
    f["structuring_cnt"] = (struct.groupby("src").size().reindex(f.index).fillna(0)
                            + struct.groupby("dst").size().reindex(f.index).fillna(0))
    months = max(days / 30.0, 1.0)
    f["income_ratio"] = (f["sum_in"] / months / acc["declared_income"].replace(0, np.nan)).fillna(0).clip(upper=500)

    # dùng chung thiết bị giữa các CHỦ SỞ HỮU khác nhau (cùng chủ thì không tính)
    dev = pd.concat([
        acc.reset_index()[["account_id", "device_id"]],
        tx[["src", "device_id"]].rename(columns={"src": "account_id"}),
    ]).drop_duplicates()
    dev = dev[~dev["account_id"].isin(sys_ids)]
    dev["holder_id"] = dev["account_id"].map(acc["holder_id"])
    holders_per_dev = dev.groupby("device_id")["holder_id"].nunique()
    dev["others"] = dev["device_id"].map(holders_per_dev) - 1
    f["shared_device_holders"] = dev.groupby("account_id")["others"].max().reindex(f.index).fillna(0)

    f["foreign_ip_ratio"] = (tx[tx["ip_country"] != "VN"].groupby("src").size() / f["n_out"].replace(0, np.nan)).reindex(f.index).fillna(0)
    f["night_ratio"] = (tx[tx["hour"] < 5].groupby("src").size() / f["n_out"].replace(0, np.nan)).reindex(f.index).fillna(0)
    cash = tx[tx["dst"].isin(sys_ids)]
    f["cashout_ratio"] = (cash.groupby("src")["amount"].sum() / f["sum_out"].replace(0, np.nan)).reindex(f.index).fillna(0)
    f["account_age_days"] = (pd.Timestamp(as_of) - pd.to_datetime(acc["open_date"])).dt.days.clip(lower=0)
    f["ekyc"] = (acc["kyc_channel"] == "EKYC").astype(int)
    f["is_business"] = acc["segment"].isin(BUSINESS_SEGMENTS).astype(int)
    tx["src_holder"] = tx["src"].map(acc["holder_id"])
    tx["dst_holder"] = tx["dst"].map(acc["holder_id"])
    same = tx[tx["src_holder"] == tx["dst_holder"]]
    f["same_holder_out_ratio"] = (same.groupby("src")["amount"].sum() / f["sum_out"].replace(0, np.nan)).reindex(f.index).fillna(0)
    f["small_in_ratio"] = (tx[tx["amount"] < 1_000_000].groupby("dst").size() / f["n_in"].replace(0, np.nan)).reindex(f.index).fillna(0)
    f["qr_in_ratio"] = (tx[tx["channel"] == "QR"].groupby("dst").size() / f["n_in"].replace(0, np.nan)).reindex(f.index).fillna(0)

    # tỷ lệ lệnh chi có nội dung trả lương (dùng cho lý do giảm nghi ngờ, không đưa vào mô hình)
    pay = tx[tx["memo"].str.lower().str.contains("luong", na=False)]
    f["payroll_out_ratio"] = (pay.groupby("src").size() / f["n_out"].replace(0, np.nan)).reindex(f.index).fillna(0)

    # giao dịch ra thực hiện từ thiết bị KHÔNG phải của chủ tài khoản -> dấu hiệu bị chiếm quyền (nạn nhân ATO)
    tx["own_dev"] = tx["src"].map(acc["device_id"])
    foreign_dev = tx[(tx["device_id"] != tx["own_dev"]) & (tx["src_holder"] != tx["dst_holder"])]
    f["foreign_device_out_ratio"] = (foreign_dev.groupby("src").size() / f["n_out"].replace(0, np.nan)).reindex(f.index).fillna(0)

    f = f.fillna(0)
    f["is_system"] = f.index.isin(sys_ids).astype(int)
    f["is_mule"] = acc["is_mule"]
    return f
