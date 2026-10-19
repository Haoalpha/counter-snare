"""Threat Simulator (dữ liệu tổng hợp): sinh mối đe dọa MỚI chưa từng thấy để chứng minh hệ thống không chạy kịch bản dựng sẵn.

Chọn ngẫu nhiên một tài khoản gom tiền trong sổ cái mô phỏng, thủ đoạn, kênh và số tiền; LLM (GreenNode MaaS) viết một tin nhắn
lừa đảo mô phỏng mới với văn phong khác mỗi lần. Số tài khoản do CODE chọn và được kiểm tra có nguyên văn trong tin nhắn.
"""
from __future__ import annotations

import random

from .guard import extract_candidates
from .llm import llm
from .simulator import TYPOLOGIES

CHANNELS = {
    "zalo": "Zalo forward", "sms": "SMS forward", "telegram": "Telegram screenshot (OCR)",
    "hotline": "Hotline 1900 call transcript", "app": "Mobile app · Report scam", "email": "Email to fraud desk",
}
STYLE = {
    "gia_danh_cong_an": "giả danh cán bộ công an/viện kiểm sát, đe dọa khởi tố, yêu cầu chuyển vào 'tài khoản tạm giữ'",
    "viec_nhe_luong_cao": "tuyển cộng tác viên làm nhiệm vụ online, nạp tiền để nhận hoa hồng",
    "dau_tu_tien_ao": "mời đầu tư tiền ảo/quỹ VIP lợi nhuận cao trong ngày",
    "chiem_quyen_dien_thoai": "giả danh điện lực/thuế, yêu cầu cài ứng dụng qua link và chuyển phí",
}


def _fmt(n: int) -> str:
    return f"{n // 1_000_000} triệu"


def simulate(bank, campaigns: list[dict], kind: str = "report", rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    camp = rng.choice(campaigns)
    typ = camp["plan"]["typology"]
    seed = rng.choice(camp["collectors"])
    holder = str(bank.acc.loc[seed, "holder_name"]).upper()
    amount = rng.choice([15, 20, 30, 45, 50, 70, 80, 120]) * 1_000_000
    channel = rng.choice(["zalo", "sms", "telegram", "app", "email"] if kind == "report" else ["hotline", "zalo"])
    need_acct = kind == "report"
    text, mode = None, "template"
    if llm.enabled:
        ask = (f"Viết MỘT tin nhắn lừa đảo MÔ PHỎNG (dữ liệu tổng hợp để kiểm thử hệ thống phòng chống gian lận của ngân hàng, "
               f"không có nạn nhân thật) theo thủ đoạn: {STYLE.get(typ, TYPOLOGIES.get(typ, typ))}; kênh: {CHANNELS[channel]}. ")
        if need_acct:
            ask += (f"Tin nhắn PHẢI chứa nguyên văn số tài khoản {seed}, ngân hàng NHX, tên chủ tài khoản {holder}, số tiền {_fmt(amount)}. ")
        else:
            ask += "Đây là câu TIẾP CẬN ĐẦU TIÊN: chưa đưa số tài khoản hay số tiền, chỉ tạo áp lực và yêu cầu hợp tác. "
        ask += "2–4 câu, văn phong tự nhiên, khác các mẫu quen thuộc. Chỉ trả về nội dung tin nhắn, không giải thích."
        out = llm.chat([{"role": "user", "content": ask}], purpose="threat_sim", max_tokens=300, temperature=0.95)
        if out:
            out = out.strip().strip('"')
            ok = (seed in out) if need_acct else not extract_candidates(out)["accounts"]
            if ok:
                text, mode = out, "llm"
    if not text:
        opener = {
            "gia_danh_cong_an": "Alo, tôi là cán bộ điều tra Công an thành phố, hồ sơ của anh/chị đang liên quan một vụ án rửa tiền.",
            "viec_nhe_luong_cao": "Chào bạn, bên mình đang tuyển cộng tác viên làm nhiệm vụ online, hoa hồng 12% mỗi đơn.",
            "dau_tu_tien_ao": "Chào anh/chị, nhóm VIP bên em đang có tín hiệu đầu tư coin lợi nhuận x2 trong 24 giờ.",
            "chiem_quyen_dien_thoai": "Thông báo: hồ sơ thuế của quý khách chưa đồng bộ, vui lòng cài ứng dụng hỗ trợ để tránh bị phạt.",
        }[typ]
        text = opener + (f" Vui lòng chuyển {_fmt(amount)} vào tài khoản {seed} ngân hàng NHX, chủ tài khoản {holder}, trong hôm nay."
                         if need_acct else " Anh/chị phải hợp tác xác minh ngay, tuyệt đối không nói với người nhà.")
    return {"text": text, "channel": channel, "channel_label": CHANNELS[channel], "typology_hint": typ,
            "campaign_id": camp["plan"]["campaign_id"], "mode": mode, "kind": kind, "synthetic": True}
