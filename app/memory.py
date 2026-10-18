"""Bộ nhớ dài hạn "dấu vân tay đường dây" (ring fingerprint).

Trên AgentBase: dùng Memory Service (MemoryClient, đặt MEMORY_ID). Cục bộ: bộ nhớ trong tiến trình.
Mục đích: khi một tài khoản/thiết bị của đường dây cũ xuất hiện lại ở vụ mới, agent nhận ra ngay.
"""
from __future__ import annotations

import os
import threading

from .audit import audit

MEMORY_ID = os.environ.get("MEMORY_ID", "")
STRATEGY_ID = os.environ.get("MEMORY_STRATEGY_ID", "default")
ACTOR = "bay-nguoc-aml-team"


class RingMemory:
    def __init__(self):
        self._local: list[dict] = []
        self._lock = threading.Lock()
        self._client = None
        if MEMORY_ID:
            try:
                from greennode_agentbase.memory import MemoryClient
                self._client = MemoryClient()
            except Exception as e:
                audit.log("memory", ok=False, error=f"init: {e}"[:200])

    @property
    def backend(self) -> str:
        return "AgentBase Memory" if self._client else "local"

    def _ns(self) -> str:
        return f"/strategies/{STRATEGY_ID}/actors/{ACTOR}"

    def remember(self, case_id: str, typology: str, accounts: list[str], devices: list[str]) -> None:
        fact = (f"Vụ {case_id}: đường dây '{typology}' gồm tài khoản {', '.join(accounts[:12])}; "
                f"thiết bị {', '.join(devices[:6]) or 'không rõ'}.")
        with self._lock:
            self._local.append({"case_id": case_id, "typology": typology, "accounts": set(accounts), "devices": set(devices), "fact": fact})
        if self._client:
            try:
                from greennode_agentbase.memory.models import MemoryRecordInsertDirectlyRequest
                self._client.insert_memory_records_directly(id=MEMORY_ID, namespace=self._ns(),
                                                            request=MemoryRecordInsertDirectlyRequest(memory_records=[fact]))
                audit.log("memory", case_id=case_id, op="remember", backend="agentbase", ok=True)
            except Exception as e:
                audit.log("memory", case_id=case_id, op="remember", backend="agentbase", ok=False, error=str(e)[:200])

    def recall(self, accounts: list[str], devices: list[str], case_id: str = "") -> list[dict]:
        hits = []
        with self._lock:
            for m in self._local:
                if m["case_id"] == case_id:
                    continue
                ov_a = m["accounts"] & set(accounts)
                ov_d = m["devices"] & set(devices)
                if ov_a or ov_d:
                    hits.append({"case_id": m["case_id"], "typology": m["typology"], "overlap_accounts": sorted(ov_a),
                                 "overlap_devices": sorted(ov_d), "fact": m["fact"], "source": "local"})
        if self._client and not hits and accounts:
            try:
                from greennode_agentbase.memory.models import MemoryRecordSearchRequest
                res = self._client.search_memory_records(id=MEMORY_ID, namespace=self._ns(),
                                                         request=MemoryRecordSearchRequest(query=" ".join(accounts[:5]), limit=5))
                for r in res or []:
                    txt = r.get("memory", "") if isinstance(r, dict) else getattr(r, "memory", str(r))
                    score = r.get("score") if isinstance(r, dict) else getattr(r, "score", None)
                    if any(a in txt for a in accounts):
                        hits.append({"fact": txt, "score": score, "source": "agentbase"})
                audit.log("memory", case_id=case_id, op="recall", backend="agentbase", ok=True, hits=len(hits))
            except Exception as e:
                audit.log("memory", case_id=case_id, op="recall", backend="agentbase", ok=False, error=str(e)[:200])
        return hits


ring_memory = RingMemory()
