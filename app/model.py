"""Mô hình chấm điểm rủi ro mule + giải thích (reason codes + occlusion).

Lựa chọn Gradient Boosting thay vì GNN có chủ đích: trên dữ liệu AML tổng hợp, các nghiên cứu gần đây
(vd. bộ sinh Tide, 2026) cho thấy LightGBM/XGBoost thường ngang hoặc vượt GNN, mà lại nhanh và dễ giải thích.
Cấu trúc đồ thị được đưa vào qua đặc trưng (fan-in, pass-through, thiết bị dùng chung) và bước mở rộng đường dây.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import FEATURE_LABELS, FEATURES

MONOTONIC = {
    "fast_out_ratio": 1, "max_senders_24h": 1, "structuring_cnt": 1, "income_ratio": 1,
    "shared_device_holders": 1, "foreign_ip_ratio": 1, "night_ratio": 1, "cashout_ratio": 1,
    "pass_through": 1, "account_age_days": -1, "median_dwell_min": -1,
    "is_business": -1, "same_holder_out_ratio": -1, "qr_in_ratio": -1,
}


class MuleModel:
    def __init__(self, clf=None, threshold: float = 0.5, medians: dict | None = None):
        self.clf = clf
        self.threshold = threshold
        self.medians = medians or {}

    def fit(self, feats: pd.DataFrame) -> "MuleModel":
        d = feats[feats["is_system"] == 0]
        X, y = d[FEATURES].values, d["is_mule"].values
        # ràng buộc đơn điệu: dấu hiệu đáng ngờ chỉ được làm TĂNG rủi ro, yếu tố hợp lệ chỉ được làm GIẢM
        # -> mô hình bền hơn trước thủ đoạn mới và giải thích được với giám khảo/thanh tra
        mono = [MONOTONIC.get(name, 0) for name in FEATURES]
        self.clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                                  min_samples_leaf=10, l2_regularization=1.0,
                                                  monotonic_cst=mono, class_weight="balanced", random_state=0)
        self.clf.fit(X, y)
        self.medians = d[d["is_mule"] == 0][FEATURES].median().to_dict()
        return self

    def predict(self, feats: pd.DataFrame) -> pd.Series:
        p = pd.Series(self.clf.predict_proba(feats[FEATURES].values)[:, 1], index=feats.index)
        p[feats["is_system"] == 1] = 0.0
        return p

    def contributions(self, row: pd.Series, top: int = 6, n_perm: int = 32) -> list[dict]:
        """Giải thích cục bộ bằng Shapley value (lấy mẫu Monte-Carlo các hoán vị, baseline = tài khoản 'bình thường'
        trung vị). Tính chất cộng: tổng đóng góp = điểm(tài khoản) − điểm(baseline). Tất định (seed cố định)."""
        x = row[FEATURES].astype(float).values
        base = np.array([self.medians.get(n, 0.0) for n in FEATURES], dtype=float)
        rng = np.random.default_rng(0)
        perms = [rng.permutation(len(FEATURES)) for _ in range(n_perm)]
        rows = []
        for perm in perms:
            z = base.copy()
            rows.append(z.copy())
            for idx in perm:
                z[idx] = x[idx]
                rows.append(z.copy())
        p = self.clf.predict_proba(np.array(rows))[:, 1]
        phi = np.zeros(len(FEATURES))
        k = 0
        for perm in perms:
            for j, idx in enumerate(perm):
                phi[idx] += p[k + j + 1] - p[k + j]
            k += len(FEATURES) + 1
        phi /= n_perm
        out = [{"feature": n, "label": FEATURE_LABELS.get(n, n), "value": float(x[i]), "normal_median": float(base[i]),
                "impact": round(float(phi[i]), 4), "method": "shapley_mc"} for i, n in enumerate(FEATURES)]
        out.sort(key=lambda d: -abs(d["impact"]))
        return out[:top]

    def save(self, path: Path) -> None:
        path.write_bytes(pickle.dumps({"clf": self.clf, "threshold": self.threshold, "medians": self.medians}))

    @staticmethod
    def load(path: Path) -> "MuleModel":
        d = pickle.loads(path.read_bytes())
        return MuleModel(d["clf"], d["threshold"], d["medians"])


def reason_codes(r: pd.Series) -> tuple[list[dict], list[dict]]:
    """Trả về (dấu hiệu đáng ngờ, yếu tố giảm nghi ngờ) có căn cứ pháp lý."""
    red, green = [], []

    def add(lst, code, text, legal):
        lst.append({"code": code, "text": text, "legal": legal})

    if r["fast_out_ratio"] >= 0.6 and r["n_out"] >= 2:
        add(red, "R_FAST", f"{r['fast_out_ratio']:.0%} số tiền được chuyển đi trong vòng 60 phút sau khi nhận "
                           f"(thời gian giữ tiền trung vị {r['median_dwell_min']:.0f} phút)",
            "Luật PCRT 2022, Điều 28: tiền vào và ra nhanh khỏi tài khoản")
    if r["max_senders_24h"] >= 4 and r["is_business"] == 0:
        add(red, "R_FANIN", f"Nhận tiền từ {int(r['max_senders_24h'])} người gửi khác nhau trong một ngày",
            "Luật PCRT 2022, Điều 28: nhiều tài khoản chuyển tiền về một tài khoản")
    if r["structuring_cnt"] >= 3 and r.get("payroll_out_ratio", 0) < 0.5:
        add(red, "R_STRUCT", f"{int(r['structuring_cnt'])} giao dịch trong khoảng 9–10 triệu đồng, dấu hiệu chia nhỏ để né "
                             "ngưỡng xác thực sinh trắc học 10 triệu", "QĐ 2345/QĐ-NHNN; Luật PCRT 2022, Điều 28")
    if r["income_ratio"] >= 5:
        add(red, "R_INCOME", f"Dòng tiền vào gấp {r['income_ratio']:.0f} lần thu nhập kê khai",
            "Luật PCRT 2022, Điều 27: số tiền lớn không phù hợp thu nhập")
    if r["shared_device_holders"] >= 1:
        add(red, "R_DEVICE", f"Dùng chung thiết bị đăng nhập với {int(r['shared_device_holders'])} chủ tài khoản khác",
            "Luật PCRT 2022, Điều 28: giao dịch trực tuyến bất thường về thiết bị")
    if r["foreign_ip_ratio"] >= 0.3:
        add(red, "R_IP", f"{r['foreign_ip_ratio']:.0%} giao dịch ra thực hiện từ địa chỉ IP nước ngoài",
            "Luật PCRT 2022, Điều 28: giao dịch từ IP ở nước ngoài")
    if r["account_age_days"] <= 90 and r["ekyc"] == 1 and r["n_in"] > 0:
        add(red, "R_NEW", f"Tài khoản mở qua eKYC, mới {int(r['account_age_days'])} ngày", "Rủi ro tài khoản thuê/mua")
    if r["cashout_ratio"] >= 0.3:
        add(red, "R_CASHOUT", f"{r['cashout_ratio']:.0%} tiền ra đi tới sàn tài sản số/rút tiền mặt",
            "Luật PCRT 2022, Điều 27–28: nguồn/đích tiền khó truy vết")
    if r["night_ratio"] >= 0.3:
        add(red, "R_NIGHT", f"{r['night_ratio']:.0%} giao dịch ra vào khung 0h–5h", "Hành vi bất thường")

    if r["is_business"] == 1 and r["qr_in_ratio"] >= 0.7:
        add(green, "G_SHOP", "Hộ kinh doanh, tiền vào chủ yếu qua QR giá trị nhỏ từ khách lẻ, phù hợp mô hình kinh doanh",
            "Phù hợp hồ sơ khách hàng (CDD)")
    if r["is_business"] == 1 and r.get("payroll_out_ratio", 0) >= 0.7:
        add(green, "G_PAYROLL", f"Doanh nghiệp chi lương định kỳ cho {int(r['uniq_receivers'])} người lao động "
                                f"({r['payroll_out_ratio']:.0%} lệnh chi có nội dung trả lương), phù hợp hoạt động kinh doanh",
            "Phù hợp hồ sơ khách hàng (CDD); không thuộc dấu hiệu Điều 27–28")
    if r["same_holder_out_ratio"] >= 0.7:
        add(green, "G_SELF", "Tiền ra chủ yếu chuyển sang tài khoản khác của chính chủ", "Phù hợp hồ sơ khách hàng (CDD)")
    if r["account_age_days"] > 365 and r["foreign_ip_ratio"] == 0 and r["shared_device_holders"] == 0:
        add(green, "G_TENURE", f"Khách hàng lâu năm ({int(r['account_age_days'] / 365)} năm), thiết bị và IP ổn định", "Lịch sử tốt")
    return red, green


def risk_band(p: float) -> str:
    if p >= 0.8:
        return "RẤT CAO"
    if p >= 0.5:
        return "CAO"
    if p >= 0.2:
        return "TRUNG BÌNH"
    return "THẤP"


def np_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)
