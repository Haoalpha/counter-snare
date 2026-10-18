"""Tool gateway + Policy (mô phỏng đúng ngữ nghĩa AgentBase MCP Gateway / Policy Group: "first match wins").

Agent CHỈ được đọc dữ liệu và soạn dự thảo. Các hành động có hậu quả pháp lý (trì hoãn giao dịch - Điều 44,
nộp báo cáo giao dịch đáng ngờ - Điều 26, phong tỏa theo quyết định cơ quan có thẩm quyền - Điều 45 Luật PCRT 2022)
bị DENY ở tầng hạ tầng, chỉ vai trò chuyên viên PCRT được ALLOW. Human-in-the-loop được ÉP BUỘC, không chỉ dựa vào prompt.
"""
from __future__ import annotations

import fnmatch

from .audit import audit

AGENT = "agent:bay-nguoc"
OFFICER = "role:aml-officer"

POLICY_GROUP = {
    "name": "pg-bay-nguoc-aml",
    "description": "Agent điều tra chỉ đọc + soạn thảo; hành động pháp lý cần chuyên viên",
    "statements": [
        {"principal": AGENT, "tool": "read_*", "effect": "ALLOW"},
        {"principal": AGENT, "tool": "draft_*", "effect": "ALLOW"},
        {"principal": AGENT, "tool": "memory_*", "effect": "ALLOW"},
        {"principal": AGENT, "tool": "delay_transactions", "effect": "DENY"},
        {"principal": AGENT, "tool": "submit_str", "effect": "DENY"},
        {"principal": AGENT, "tool": "freeze_account", "effect": "DENY"},
        {"principal": OFFICER, "tool": "*", "effect": "ALLOW"},
        {"principal": "*", "tool": "*", "effect": "DENY"},
    ],
}

TOOL_DESCRIPTIONS = {
    "read_account_profile": "Đọc hồ sơ KYC (che tên) của một tài khoản",
    "read_transactions": "Đọc lịch sử giao dịch của một tài khoản",
    "read_expand_network": "Mở rộng đồ thị dòng tiền + thiết bị từ tài khoản hạt giống",
    "read_risk_score": "Điểm rủi ro mule + lý do",
    "read_simo_lookup": "Tra cứu danh sách tài khoản nghi gian lận (mock SIMO)",
    "read_regulations": "Tra cứu căn cứ pháp lý (RAG)",
    "draft_str": "Soạn DỰ THẢO báo cáo giao dịch đáng ngờ",
    "memory_recall": "Truy hồi hồ sơ đường dây đã biết",
    "memory_remember": "Lưu dấu vân tay đường dây",
    "delay_transactions": "Trì hoãn giao dịch (Điều 44 Luật PCRT, ≤ 03 ngày làm việc)",
    "submit_str": "Nộp báo cáo giao dịch đáng ngờ tới NHNN (Điều 26, thời hạn Điều 37)",
    "freeze_account": "Phong tỏa tài khoản theo quyết định của cơ quan có thẩm quyền (Điều 45)",
}


class PolicyDenied(Exception):
    pass


def evaluate(principal: str, tool: str) -> tuple[str, dict]:
    for st in POLICY_GROUP["statements"]:
        if fnmatch.fnmatch(principal, st["principal"]) and fnmatch.fnmatch(tool, st["tool"]):
            return st["effect"], st
    return "DENY", {}


def call_tool(principal: str, tool: str, fn, *args, case_id: str = "", **kwargs):
    effect, st = evaluate(principal, tool)
    audit.log("policy", case_id=case_id, principal=principal, tool=tool, effect=effect,
              matched=f"{st.get('principal')} / {st.get('tool')}" if st else "default")
    if effect != "ALLOW":
        raise PolicyDenied(f"{principal} không có quyền gọi '{tool}' (policy {POLICY_GROUP['name']}: {effect})")
    result = fn(*args, **kwargs)
    audit.log("tool_call", case_id=case_id, principal=principal, tool=tool)
    return result
