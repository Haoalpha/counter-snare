"""Nhật ký kiểm toán: mọi lệnh gọi LLM, lệnh gọi tool, quyết định policy, sự kiện guardrail và phê duyệt của con người."""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime


class Audit:
    def __init__(self, maxlen: int = 2000):
        self._events: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def log(self, kind: str, **data) -> dict:
        ev = {"ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}
        with self._lock:
            self._events.append(ev)
        if data.get("case_id"):  # chuyển tiếp sang Agentic Thought Stream của vụ việc
            from .events import emit
            payload = {k: v for k, v in data.items() if k != "case_id"}
            if "type" in payload:
                payload["subtype"] = payload.pop("type")
            emit(data["case_id"], type="audit", kind=kind, **payload)
        return ev

    def list(self, case_id: str | None = None, limit: int = 300) -> list[dict]:
        with self._lock:
            evs = list(self._events)
        if case_id:
            evs = [e for e in evs if e.get("case_id") == case_id]
        return evs[-limit:]


audit = Audit()
