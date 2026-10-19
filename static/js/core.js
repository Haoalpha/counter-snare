// Shared helpers: API client, escaping, formatting, labels (English UI, Vietnamese legal content).
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

export const vnd = (n) => (Math.round(n) || 0).toLocaleString("vi-VN") + " ₫";
export const vndShort = (n) => n >= 1e9 ? (n / 1e9).toFixed(2) + "B ₫" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M ₫" : vnd(n);
export const pct = (x, d = 0) => (x * 100).toFixed(d) + "%";

export const icons = () => { try { window.lucide && window.lucide.createIcons(); } catch (e) { /* ignore */ } };

export function busy(btn, on, label) {
  if (on) { btn.dataset.l = btn.innerHTML; btn.innerHTML = `<span class="spinner"></span>${esc(label)}`; btn.disabled = true; }
  else if (btn.dataset.l) { btn.innerHTML = btn.dataset.l; btn.disabled = false; icons(); }
}

export function toast(msg, kind = "info") {
  const t = $("#toast");
  t.className = "toast" + (kind === "error" ? " error" : "");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.hidden = true; }, 4200);
}

// Graph roles: categorical colour + distinct shape (never colour alone)
export const ROLE = {
  collector: { en: "Collection Hub", color: "#BE123C", shape: "diamond", badge: "b-rose" },
  layer: { en: "Transit Mule", color: "#D97706", shape: "dot", badge: "b-amber" },
  cashout: { en: "Cash-out Point", color: "#7C3AED", shape: "triangle", badge: "b-purple" },
  victim: { en: "Victim", color: "#0284C7", shape: "square", badge: "b-cyan" },
  victim_ato: { en: "Compromised Account", color: "#0891B2", shape: "triangleDown", badge: "b-cyan" },
  sink: { en: "Crypto Off-ramp / ATM", color: "#64748B", shape: "box", badge: "b-slate" },
  related: { en: "Related", color: "#A08C93", shape: "dot", badge: "b-slate" },
};

// Agent roster: avatar colour + icon (Lucide)
export const AGENTS = {
  "Orchestrator": { icon: "workflow", c: "#7A1238" },
  "Guardrail Agent": { icon: "shield-half", c: "#047857" },
  "Intel Agent": { icon: "scan-search", c: "#0369A1" },
  "Ring Hunter": { icon: "network", c: "#BE123C" },
  "Risk Engine": { icon: "gauge", c: "#B45309" },
  "Decoy Agent": { icon: "fish", c: "#A16207" },
  "Investigator Agent": { icon: "file-pen-line", c: "#4338CA" },
  "Judge Agent": { icon: "scale", c: "#0F766E" },
  "Policy Gateway": { icon: "lock-keyhole", c: "#5A0F2E" },
  "Memory Agent": { icon: "database", c: "#7E22CE" },
  "Triage Agent": { icon: "filter", c: "#047857" },
  "Analyst Copilot": { icon: "sparkles", c: "#334155" },
};
export const avatar = (name, cls = "av") => { const a = AGENTS[name] || { icon: "bot", c: "#7B5E68" };
  return `<span class="${cls}" style="--c:${a.c}"><i data-lucide="${a.icon}"></i></span>`; };

export const MODEL_SHORT = { "z-ai/glm-5.3-flash-thirdparty": "GLM 5.3 Flash", "z-ai/glm-5.2-hackathon": "GLM 5.2", "qwen/qwen3.8-flash": "Qwen 3.8 Flash", "google/gemma-4-31b-it": "Gemma 4 31B" };

export function englishStatus(s) {
  if (/ĐÃ DUYỆT bởi/.test(s)) return "APPROVED · " + s.replace(/^ĐÃ DUYỆT bởi\s*/, "").replace(" – đã nộp NHNN (mô phỏng)", " · filed (simulated)");
  if (/TỪ CHỐI bởi/.test(s)) return "REJECTED · " + s.replace(/^TỪ CHỐI bởi\s*/, "");
  return { "CHỜ CHUYÊN VIÊN DUYỆT": "PENDING OFFICER APPROVAL", "KHUYẾN NGHỊ": "RECOMMENDED", "CẦN QUYẾT ĐỊNH CƠ QUAN CÓ THẨM QUYỀN": "REQUIRES AUTHORITY DECISION" }[s] || s;
}

export const TYPOLOGY_EN = {
  gia_danh_cong_an: "Law-enforcement impersonation scam",
  viec_nhe_luong_cao: "Task / job scam (escalating deposits)",
  dau_tu_tien_ao: "Crypto investment scam",
  chiem_quyen_dien_thoai: "Malware account takeover (fake utility app)",
  canh_bao_giam_sat: "Transaction-monitoring alert (internal)",
  khac: "Unclassified",
};

export const FEATURE_EN = {
  fast_out_ratio: "Funds forwarded < 60 min", median_dwell_min: "Median holding time (min)", max_senders_24h: "Distinct senders / 24h",
  structuring_cnt: "Sub-10M structuring (biometric evasion)", income_ratio: "Inflow vs declared income", shared_device_holders: "Shared device (other holders)",
  foreign_ip_ratio: "Foreign-IP sessions", night_ratio: "00:00–05:00 activity", cashout_ratio: "Crypto / ATM cash-out share",
  account_age_days: "Account age (days)", pass_through: "Pass-through ratio", uniq_senders: "Unique senders", uniq_receivers: "Unique receivers",
  is_business: "Registered business", same_holder_out_ratio: "Transfers to own accounts", small_in_ratio: "Small-ticket inflows", qr_in_ratio: "QR merchant inflows",
  ekyc: "eKYC-onboarded", n_in: "Inbound tx", n_out: "Outbound tx", log_sum_in: "Total inflow (log)",
};

export const STEP_EN = [
  ["Guardrail", "Zero-Trust Guardrails"], ["Intel Agent", "Intel Agent · seed extraction"], ["Mule Ring Hunter", "Mule Ring Hunter · graph + GBM"],
  ["Investigator Agent", "Investigator Agent · STR synthesis"], ["Judge Agent", "Agent-as-a-Judge · fact-check"],
  ["Đề xuất hành động", "Policy Gateway · action proposal"], ["Lưu dấu vân tay", "AgentBase Memory · ring fingerprint"],
  ["Đóng cảnh báo", "False-positive closure"],
];
export const stepEn = (vi) => (STEP_EN.find(([k]) => vi.startsWith(k)) || [null, vi])[1];

export const DECISION_EN = {
  "ĐÓNG (DƯƠNG TÍNH GIẢ)": ["AUTO-CLOSED · FALSE POSITIVE", "b-emerald"],
  "LEO THANG": ["ESCALATED", "b-rose"],
  "CHUYỂN BẢO VỆ NẠN NHÂN": ["VICTIM PROTECTION", "b-cyan"],
  "NGƯỜI XEM XÉT": ["HUMAN REVIEW", "b-amber"],
};

export const TOOL_EN = {
  submit_str: { label: "Direct Submit STR to FIU", legal: "Luật PCRT 2022 – Điều 26 (báo cáo giao dịch đáng ngờ), thời hạn Điều 37" },
  delay_transactions: { label: "Delay Transactions", legal: "Luật PCRT 2022 – Điều 44 (trì hoãn giao dịch, tối đa 03 ngày làm việc)" },
  freeze_account: { label: "Instant Account Freeze", legal: "Luật PCRT 2022 – Điều 45 (phong tỏa chỉ theo quyết định của cơ quan có thẩm quyền)" },
  dismiss_alert: { label: "Dismiss False Positive", legal: "Lưu hồ sơ rà soát nội bộ" },
  notify_victims: { label: "Notify Victim Customers", legal: "Bảo vệ khách hàng" },
};

export const state = { meta: null };
