"""Event bus cho Agentic Thought Stream: mọi agent / tool call / lệnh gọi LLM / quyết định policy của một vụ việc
được phát ra theo thời gian thực để giao diện hiển thị trực tiếp (không đợi kết quả cuối)."""
from __future__ import annotations

import threading
import time

_subs: dict[str, list] = {}
_lock = threading.Lock()


def subscribe(case_id: str, fn) -> None:
    with _lock:
        _subs.setdefault(case_id, []).append(fn)


def unsubscribe(case_id: str) -> None:
    with _lock:
        _subs.pop(case_id, None)


def emit(case_id: str, **event) -> None:
    if not case_id:
        return
    event.setdefault("ts", round(time.time(), 3))
    with _lock:
        fns = list(_subs.get(case_id, []))
    for fn in fns:
        try:
            fn(event)
        except Exception:
            pass
