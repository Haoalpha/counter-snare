"""Kho tri thức pháp lý (RAG) để agent trích dẫn đúng căn cứ. Embedding: BAAI bge-m3 trên GreenNode MaaS;
dự phòng: so khớp từ khóa khi chưa có API key.

Nội dung là TÓM TẮT diễn giải để tham khảo nghiệp vụ, không thay thế văn bản gốc.
"""
from __future__ import annotations

import math
import os
import re

from .audit import audit

DOCS = [
    {"id": "PCRT-26", "title": "Luật PCRT 2022 (14/2022/QH15) – Điều 26: Báo cáo giao dịch đáng ngờ",
     "text": "Đối tượng báo cáo phải báo cáo Ngân hàng Nhà nước khi biết hoặc có cơ sở hợp lý để nghi ngờ tài sản trong giao dịch "
             "có nguồn gốc từ hoạt động phạm tội hoặc liên quan đến rửa tiền, bao gồm giao dịch có dấu hiệu đáng ngờ quy định tại các Điều 27 đến 33."},
    {"id": "PCRT-27", "title": "Luật PCRT 2022 – Điều 27: Dấu hiệu đáng ngờ cơ bản",
     "text": "Khách hàng cung cấp thông tin không chính xác/không đầy đủ; không xác định được danh tính; số điện thoại không liên lạc được; "
             "giao dịch liên quan hoạt động phạm tội; số tiền lớn không phù hợp với thu nhập hoặc hoạt động kinh doanh của khách hàng."},
    {"id": "PCRT-28", "title": "Luật PCRT 2022 – Điều 28: Dấu hiệu đáng ngờ trong lĩnh vực ngân hàng",
     "text": "Doanh số giao dịch biến động đột biến; tiền vào và ra nhanh khỏi tài khoản; nhiều tài khoản chuyển tiền giá trị nhỏ về một tài khoản "
             "hoặc ngược lại; mở nhiều tài khoản ở khu vực khác nơi cư trú; nhận khoản tiền lớn bất thường; giao dịch trực tuyến liên tục thay đổi "
             "thiết bị hoặc địa chỉ IP ở nước ngoài."},
    {"id": "PCRT-37", "title": "Luật PCRT 2022 – Điều 37: Thời hạn báo cáo",
     "text": "Giao dịch đáng ngờ phải báo cáo trong thời hạn 03 ngày làm việc kể từ ngày phát sinh giao dịch hoặc 01 ngày làm việc kể từ ngày phát hiện. "
             "Trường hợp giao dịch đáng ngờ có dấu hiệu liên quan tội phạm do khách hàng yêu cầu, báo cáo trong 24 giờ kể từ khi phát hiện "
             "cho cơ quan nhà nước có thẩm quyền và Ngân hàng Nhà nước."},
    {"id": "PCRT-44", "title": "Luật PCRT 2022 – Điều 44: Trì hoãn giao dịch",
     "text": "Đối tượng báo cáo áp dụng ngay biện pháp trì hoãn giao dịch khi các bên liên quan thuộc Danh sách đen, có lý do để tin giao dịch liên quan "
             "hoạt động phạm tội, hoặc theo yêu cầu của cơ quan nhà nước có thẩm quyền; báo cáo ngay cho cơ quan có thẩm quyền và NHNN. "
             "Thời hạn trì hoãn không quá 03 ngày làm việc. Đối tượng báo cáo không chịu trách nhiệm về hậu quả nếu áp dụng đúng quy định."},
    {"id": "PCRT-45", "title": "Luật PCRT 2022 – Điều 45: Phong tỏa tài khoản, niêm phong, tạm giữ tài sản",
     "text": "Đối tượng báo cáo thực hiện phong tỏa tài khoản, niêm phong, phong tỏa hoặc tạm giữ tài sản theo QUYẾT ĐỊNH của cơ quan nhà nước có thẩm quyền. "
             "Ngân hàng không tự ý phong tỏa nếu chưa có quyết định."},
    {"id": "QD-2345", "title": "Quyết định 2345/QĐ-NHNN – Xác thực sinh trắc học",
     "text": "Từ 01/7/2024, giao dịch chuyển tiền điện tử của cá nhân trên 10 triệu đồng/lần hoặc tổng trên 20 triệu đồng/ngày phải xác thực sinh trắc học. "
             "Hệ quả: đường dây mule có xu hướng chia nhỏ giao dịch dưới 10 triệu để né xác thực."},
    {"id": "SIMO", "title": "Hệ thống SIMO của NHNN",
     "text": "Hệ thống giám sát, quản lý, hỗ trợ phòng ngừa rủi ro gian lận: ghi nhận tài khoản/ví/thẻ nghi gian lận, cảnh báo khách hàng trước khi chuyển tiền. "
             "Đến 29/6/2026 đã gửi cảnh báo tới 4,6 triệu lượt khách hàng, hơn 1,5 triệu lượt dừng/hủy giao dịch, bảo vệ hơn 5.200 tỷ đồng."},
    {"id": "BCA-NHNN", "title": "Quy chế phối hợp NHNN – Bộ Công an về phòng, chống lừa đảo trực tuyến",
     "text": "Ngày 23/6/2026 NHNN và Bộ Công an ký kết, triển khai kế hoạch thực hiện quy chế phối hợp phòng, chống lừa đảo trực tuyến; "
             "là căn cứ để chia sẻ thông tin tài khoản nghi lừa đảo và phối hợp xử lý."},
    {"id": "PDP-2025", "title": "Luật Bảo vệ dữ liệu cá nhân 2025",
     "text": "Dữ liệu cá nhân của khách hàng phải được xử lý đúng mục đích, tối thiểu hóa, bảo mật; áp dụng che/ẩn danh khi chuyển cho hệ thống AI; "
             "lưu vết truy cập. Hệ thống chỉ dùng dữ liệu tổng hợp trong môi trường thi."},
]


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


class Knowledge:
    def __init__(self):
        self._emb = None
        self._qcache: dict[str, list] = {}
        self._client = None
        key = os.environ.get("LLM_API_KEY", "")
        if key:
            from openai import OpenAI
            self._client = OpenAI(base_url=os.environ.get("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"),
                                  api_key=key, timeout=30, max_retries=0)
        self.model = os.environ.get("EMBED_MODEL", "baai/bge-m3")

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self._client:
            return None
        try:
            r = self._client.embeddings.create(model=self.model, input=texts)
            audit.log("embedding", model=self.model, n=len(texts), ok=True)
            return [d.embedding for d in r.data]
        except Exception as e:
            audit.log("embedding", model=self.model, ok=False, error=str(e)[:200])
            return None

    def search(self, query: str, k: int = 3) -> list[dict]:
        if self._client and self._emb is None:
            self._emb = self._embed([d["title"] + ". " + d["text"] for d in DOCS]) or []
        if self._emb:
            q = self._qcache.get(query) or self._embed([query])
            if q:
                self._qcache[query] = q
            if q:
                qv = q[0]
                scores = [sum(a * b for a, b in zip(qv, dv)) / (math.sqrt(sum(a * a for a in qv)) * math.sqrt(sum(b * b for b in dv)) + 1e-9)
                          for dv in self._emb]
                order = sorted(range(len(DOCS)), key=lambda i: -scores[i])[:k]
                return [DOCS[i] | {"score": round(scores[i], 3), "method": "bge-m3"} for i in order]
        qt = set(_tokens(query))
        scored = [(len(qt & set(_tokens(d["title"] + " " + d["text"]))), d) for d in DOCS]
        scored.sort(key=lambda x: -x[0])
        return [d | {"score": s, "method": "keyword"} for s, d in scored[:k]]

    def get(self, doc_id: str) -> dict | None:
        return next((d for d in DOCS if d["id"] == doc_id), None)


knowledge = Knowledge()
