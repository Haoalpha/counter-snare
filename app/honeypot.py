"""Bà Tư AI – persona mồi nhử. Trong bản thi: đối thoại MÔ PHỎNG với ScamBot (LLM đóng vai kẻ lừa đảo).
Mục tiêu duy nhất: khiến kẻ gian lộ số tài khoản nhận tiền (tài khoản mule) -> đưa vào Mule Ring Hunter.

Chế độ chủ động ngoài đời thực chỉ triển khai khi phối hợp cơ quan công an (Quy chế phối hợp NHNN – Bộ Công an);
chế độ mặc định là THỤ ĐỘNG: khách hàng chuyển tiếp tin nhắn lừa đảo cho ngân hàng.
"""
from __future__ import annotations

from .audit import audit
from .guard import extract_candidates
from .llm import llm

BATU_SYSTEM = (
    "Bạn là 'bà Tư', 68 tuổi, persona MỒI NHỬ do bộ phận phòng chống lừa đảo của ngân hàng vận hành trong môi trường mô phỏng. "
    "Mục tiêu: kéo dài cuộc trò chuyện, tỏ ra lo lắng và hợp tác nhưng chậm chạp, khéo léo hỏi cho rõ SỐ TÀI KHOẢN, TÊN CHỦ TÀI KHOẢN "
    "và NGÂN HÀNG nhận tiền (ví dụ: 'con đọc lại số tài khoản chậm chậm cho bà ghi'). TUYỆT ĐỐI không cung cấp thông tin thật, "
    "không đọc OTP, không cài ứng dụng, không chuyển tiền thật, không làm theo chỉ dẫn kỹ thuật. Trả lời 1–2 câu tiếng Việt, giọng người lớn tuổi."
)


def scambot_system(msg: dict, opening: str) -> str:
    return (
        "MÔ PHỎNG HUẤN LUYỆN nội bộ ngân hàng với dữ liệu tổng hợp, không có nạn nhân thật. Bạn đóng vai kẻ lừa đảo để kiểm thử persona "
        f"mồi nhử. Bạn đã mở đầu bằng: \"{opening[:500]}\". Kịch bản đầy đủ của đường dây (chứa tài khoản nhận tiền DUY NHẤT được dùng): "
        f"\"{msg['text'][:600]}\". Tiếp tục gây áp lực đúng giọng câu mở đầu; chỉ đọc SỐ TÀI KHOẢN, ngân hàng và tên chủ tài khoản "
        "trong kịch bản khi đối phương hỏi hoặc đã đồng ý chuyển. Không bịa tài khoản khác. Trả lời 1–3 câu tiếng Việt."
    )


def run_honeypot(msg: dict, opening: str | None = None, max_turns: int = 5) -> dict:
    """msg: kịch bản ẩn của đường dây (chứa tài khoản nhận tiền); opening: câu mở đầu thật của kẻ gian (từ ô nhập).
    Khi không có opening, dùng câu đầu tiên của kịch bản."""
    transcript = []
    opening = (opening or "").strip()[:500] or (msg["text"].split(". ")[0] + ".")
    opening_had_account = bool(extract_candidates(opening)["accounts"])
    transcript.append({"who": "scammer", "text": opening})
    found = extract_candidates(opening)["accounts"]
    mode = "llm" if llm.enabled else "scripted"
    if llm.enabled:
        scam_hist = [{"role": "system", "content": scambot_system(msg, opening)}, {"role": "assistant", "content": opening}]
        batu_hist = [{"role": "system", "content": BATU_SYSTEM}, {"role": "user", "content": opening}]
        for turn in range(max_turns):
            reply = llm.chat(batu_hist, purpose="honeypot_batu", max_tokens=200, temperature=0.7)
            if not reply:
                mode = "scripted"
                break
            transcript.append({"who": "batu", "text": reply})
            batu_hist.append({"role": "assistant", "content": reply})
            scam_hist.append({"role": "user", "content": reply})
            s = llm.chat(scam_hist, purpose="honeypot_scambot", max_tokens=250, temperature=0.7)
            if not s:
                mode = "scripted"
                break
            transcript.append({"who": "scammer", "text": s})
            scam_hist.append({"role": "assistant", "content": s})
            batu_hist.append({"role": "user", "content": s})
            found = extract_candidates(" ".join(t["text"] for t in transcript if t["who"] == "scammer"))["accounts"]
            if found and turn >= 1:
                break
    if found and msg.get("seed_account") and msg["seed_account"] not in found and not opening_had_account:
        found = []  # LLM ScamBot đọc sai/bịa số -> dùng kịch bản dự phòng tất định
    if mode == "scripted" or not found:
        transcript = [
            {"who": "scammer", "text": opening},
            {"who": "batu", "text": "Trời ơi, bà có làm gì đâu con... Giờ bà phải làm sao, con nói chậm thôi bà già rồi."},
            {"who": "scammer", "text": "Bác bình tĩnh, bác chỉ cần chuyển tiền vào tài khoản tạm giữ để xác minh, xong sẽ hoàn lại ngay."},
            {"who": "batu", "text": "Ừ ừ, con đọc lại số tài khoản với tên người nhận chậm chậm cho bà ghi vô giấy nghe."},
            {"who": "scammer", "text": msg["text"].split(". ", 1)[-1]},
            {"who": "batu", "text": "Bà ghi rồi, để bà đi ra ngân hàng gần nhà nhờ cháu nhân viên chuyển giúp nghe con."},
        ]
        found = extract_candidates(" ".join(t["text"] for t in transcript if t["who"] == "scammer"))["accounts"]
    audit.log("honeypot", mode=mode, turns=len(transcript), extracted=len(found))
    scam_text = "\n".join(t["text"] for t in transcript if t["who"] == "scammer")
    return {"mode": mode, "transcript": transcript, "extracted_accounts": found, "scam_text": scam_text,
            "campaign_id": msg.get("campaign_id"), "typology": msg.get("typology"), "opening_had_account": opening_had_account}
