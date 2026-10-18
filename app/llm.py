"""LLM Gateway cho GreenNode MaaS (OpenAI-compatible):

- ĐỊNH TUYẾN THEO TÁC VỤ (model routing, ý tưởng giống nền tảng đa-model "LLM Suite" của JPMorgan): mỗi tác vụ có
  thứ tự model riêng – soạn STR dùng model mạnh có suy luận, tác vụ nhanh dùng model nhẹ.
- TUÂN THỦ RATE LIMIT BTC (theo user): GLM 5.2 = 15 RPM, GLM 5.3 Flash = 10 RPM, Qwen 3.8 Flash = 10 RPM, Gemma 4 = 15 RPM.
  Bộ giới hạn cửa sổ trượt 60 giây cho từng model (để dư 1 request an toàn); hết hạn mức thì chuyển model kế tiếp,
  tất cả đều hết thì chờ có giới hạn, quá thời gian thì hệ thống tự rơi về chế độ template tất định (không bao giờ "chết").
- Nhật ký kiểm toán cho mọi lệnh gọi (model, độ trễ, token).
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque

from .audit import audit

DEFAULT_BASE_URL = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
GLM53 = "z-ai/glm-5.3-flash-thirdparty"
GLM52 = "z-ai/glm-5.2-hackathon"
QWEN = "qwen/qwen3.8-flash"
GEMMA = "google/gemma-4-31b-it"

# Hạn mức BTC công bố (RPM theo user)
OFFICIAL_RPM = {GLM52: 15, GLM53: 10, QWEN: 10, GEMMA: 15}

ROUTES = {
    # Đo thực tế trên MaaS: Qwen (tắt suy luận) ~10s cho STR; GLM suy luận 60–90s -> chỉ dùng làm dự phòng cho tác vụ tương tác
    "write_str": [QWEN, GEMMA, GLM53, GLM52],
    "red_planner": [QWEN, GLM52, GEMMA, GLM53],        # sáng tạo chiến lược né tránh
    "intel_extract": [QWEN, GEMMA, GLM53, GLM52],      # trích xuất có cấu trúc, nhanh
    "judge": [GEMMA, QWEN, GLM52, GLM53],              # chấm rubric, nhanh
    "honeypot_batu": [GEMMA, QWEN, GLM52],             # hội thoại nhiều lượt -> model nhanh
    "honeypot_scambot": [QWEN, GEMMA, GLM52],
    "default": [GLM53, QWEN, GEMMA, GLM52],
}
EXTRA_BODY = {QWEN: {"enable_thinking": False}}       # tắt suy luận để giảm độ trễ (GLM không hỗ trợ tắt)
REASONING_MODELS = {GLM53, GLM52}                    # token suy luận tính vào max_tokens -> cộng thêm ngân sách


class RateLimiter:
    """Cửa sổ trượt 60 giây cho từng model."""

    def __init__(self, rpm: dict[str, int], margin: int = 1):
        self.rpm = {m: max(1, v - margin) for m, v in rpm.items()}
        self.calls: dict[str, deque] = {m: deque() for m in rpm}
        self.cooldown: dict[str, float] = {}
        self.lock = threading.Lock()

    def _prune(self, m: str, now: float) -> None:
        q = self.calls.setdefault(m, deque())
        while q and now - q[0] >= 60:
            q.popleft()

    def try_acquire(self, m: str) -> bool:
        with self.lock:
            now = time.time()
            if self.cooldown.get(m, 0) > now:
                return False
            self._prune(m, now)
            if len(self.calls[m]) < self.rpm.get(m, 5):
                self.calls[m].append(now)
                return True
            return False

    def wait_time(self, m: str) -> float:
        with self.lock:
            now = time.time()
            self._prune(m, now)
            cd = max(0.0, self.cooldown.get(m, 0) - now)
            if len(self.calls[m]) < self.rpm.get(m, 5):
                return cd
            return max(cd, 60 - (now - self.calls[m][0]) + 0.05)

    def penalize(self, m: str, seconds: float = 20) -> None:
        with self.lock:
            self.cooldown[m] = time.time() + seconds

    def snapshot(self) -> dict:
        with self.lock:
            now = time.time()
            out = {}
            for m in self.rpm:
                self._prune(m, now)
                out[m] = {"used_last_60s": len(self.calls[m]), "limit_rpm": OFFICIAL_RPM.get(m), "guard_rpm": self.rpm[m],
                          "cooldown_s": round(max(0.0, self.cooldown.get(m, 0) - now), 1)}
            return out


class LLM:
    def __init__(self):
        self.base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.timeout = float(os.environ.get("LLM_TIMEOUT", "40"))
        self.max_wait = float(os.environ.get("LLM_MAX_WAIT", "25"))
        rpm = dict(OFFICIAL_RPM)
        for item in os.environ.get("LLM_RPM", "").split(","):  # ghi đè dạng model=rpm nếu BTC đổi hạn mức
            if "=" in item:
                k, v = item.split("=", 1)
                rpm[k.strip()] = int(v)
        self.limiter = RateLimiter(rpm)
        self.models = list(OFFICIAL_RPM)
        self._client = None
        if self.api_key:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout, max_retries=0)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _pick(self, route: list[str]) -> str | None:
        for m in route:
            if self.limiter.try_acquire(m):
                return m
        waits = sorted((self.limiter.wait_time(m), m) for m in route)
        w, m = waits[0]
        if w <= self.max_wait:
            audit.log("rate_limit", model=m, action="wait", seconds=round(w, 1))
            time.sleep(w)
            if self.limiter.try_acquire(m):
                return m
        audit.log("rate_limit", action="exhausted", route=route)
        return None

    def chat(self, messages: list[dict], purpose: str, max_tokens: int = 1500, temperature: float = 0.2,
             case_id: str = "") -> str | None:
        if not self.enabled:
            return None
        route = ROUTES.get(purpose, ROUTES["default"])
        tried: set[str] = set()
        for _ in range(len(route)):
            model = self._pick([m for m in route if m not in tried])
            if not model:
                return None
            tried.add(model)
            t0 = time.time()
            try:
                budget = max_tokens + (3000 if model in REASONING_MODELS else 0)
                resp = self._client.chat.completions.create(model=model, messages=messages, max_tokens=budget,
                                                            temperature=temperature, extra_body=EXTRA_BODY.get(model) or None)
                text = (resp.choices[0].message.content or "").strip()
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
                usage = getattr(resp, "usage", None)
                audit.log("llm_call", case_id=case_id, purpose=purpose, model=model, ok=bool(text),
                          latency_ms=int((time.time() - t0) * 1000),
                          prompt_tokens=getattr(usage, "prompt_tokens", None),
                          completion_tokens=getattr(usage, "completion_tokens", None))
                if text:
                    return text
            except Exception as e:  # 429 / lỗi mạng -> phạt model này, chuyển model kế tiếp
                err = f"{type(e).__name__}: {str(e)[:200]}"
                if "429" in err or "rate" in err.lower():
                    self.limiter.penalize(model, 30)
                audit.log("llm_call", case_id=case_id, purpose=purpose, model=model, ok=False,
                          latency_ms=int((time.time() - t0) * 1000), error=err)
        return None

    def chat_json(self, messages: list[dict], purpose: str, **kw) -> dict | None:
        text = self.chat(messages, purpose, **kw)
        return parse_json(text) if text else None


def parse_json(text: str) -> dict | None:
    import json
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


llm = LLM()
