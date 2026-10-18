// TAB 4 — Governance & Observability (bento grid): runtime telemetry, MaaS gateway & RPM, audit trail, policy, architecture
import { $, api, esc, icons, state } from "./core.js";

const SHORT = { "z-ai/glm-5.3-flash-thirdparty": "GLM 5.3 Flash", "z-ai/glm-5.2-hackathon": "GLM 5.2", "qwen/qwen3.8-flash": "Qwen 3.8 Flash", "google/gemma-4-31b-it": "Gemma 4 (31B)" };
let timer = null;
let healthMs = null;

export function initGovernance() {
  renderPolicy();
  renderArchitecture();
  refresh();
  clearInterval(timer);
  timer = setInterval(() => { if (!$("#tab-governance").classList.contains("hidden")) refresh(); }, 4000);
}

async function refresh() {
  const t0 = performance.now();
  let healthOk = false;
  try { const r = await fetch("/health"); healthOk = r.ok; healthMs = Math.round(performance.now() - t0); } catch (e) { healthOk = false; }
  const [st, au] = await Promise.all([api("/api/llm_status"), api("/api/audit?limit=300")]);
  renderRuntime(healthOk, au.events);
  renderGateway(st, au.events);
  renderAudit(au.events);
}

function row(label, value, ok = null) {
  return `<div class="flex items-center justify-between gap-3 border-b border-slate-800/60 pb-2"><span class="text-slate-500">${label}</span>
    <span class="flex items-center gap-1.5 text-right text-slate-200">${ok === null ? "" : `<span class="inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-rose-500"}"></span>`}${value}</span></div>`;
}

function renderRuntime(healthOk, events) {
  const rt = state.meta.runtime || {};
  const cases = events.filter((e) => e.kind === "case_end").length;
  const host = rt.endpoint ? rt.endpoint.replace(/^https?:\/\//, "").split(".")[0] : "localhost";
  $("#runtime").innerHTML =
    row("Platform", esc(rt.platform || "GreenNode AgentBase Runtime"), true) +
    row("Container", `<span class="font-mono text-[12px]">python:3.12-slim · :${rt.port || 8080}</span>`) +
    row("Health probe", `<span class="font-mono text-[12px]">GET /health → ${healthOk ? "200" : "FAIL"}${healthMs !== null ? ` · ${healthMs} ms` : ""}</span>`, healthOk) +
    row("Endpoint", `<span class="font-mono text-[11px]">${esc(host)}</span>`) +
    row("Agent identity (IAM)", rt.agent_identity ? "injected by runtime" : "local mode", rt.agent_identity || null) +
    row("AgentBase Memory", `<span class="font-mono text-[11px]">bay-nguoc-rings</span> · ${esc(state.meta.memory_backend === "AgentBase Memory" ? "Active" : "local fallback")}`, state.meta.memory_backend === "AgentBase Memory") +
    row("Risk model", esc(rt.model_version || "v2")) +
    row("Booted", `<span class="font-mono text-[12px]">${esc(rt.started_at || "")}</span>`) +
    row("Cases this session", `<span class="font-mono">${cases}</span>`);
}

function renderGateway(st, events) {
  const rl = st.rate_limits || {};
  const emb = events.filter((e) => e.kind === "embedding");
  $("#rpm").innerHTML = Object.entries(rl).map(([m, v]) => {
    const ratio = Math.min(1, v.used_last_60s / v.limit_rpm);
    const col = ratio >= 0.9 ? "#f43f5e" : ratio >= 0.6 ? "#f59e0b" : "#34d399";
    return `<div><div class="flex justify-between text-[12px]"><span class="text-slate-300">${esc(SHORT[m] || m)} <span class="font-mono text-[10.5px] text-slate-500">${esc(m)}</span></span>
      <span class="font-mono"><b style="color:${col}">${v.used_last_60s}</b><span class="text-slate-500"> / ${v.limit_rpm} RPM · guard ${v.guard_rpm}${v.cooldown_s ? ` · cooldown ${v.cooldown_s}s` : ""}</span></span></div>
      <div class="bar-track mt-1"><div class="bar-fill" style="width:${Math.max(2, ratio * 100)}%;background:${col}"></div></div></div>`;
  }).join("") + `<div><div class="flex justify-between text-[12px]"><span class="text-slate-300">bge-m3 <span class="font-mono text-[10.5px] text-slate-500">baai/bge-m3 · embeddings (RAG, cached)</span></span>
      <span class="font-mono text-slate-400">${emb.length} calls</span></div><div class="bar-track mt-1"><div class="bar-fill" style="width:${Math.min(100, emb.length * 10)}%;background:#22d3ee"></div></div></div>`;
  const calls = events.filter((e) => e.kind === "llm_call");
  const ok = calls.filter((e) => e.ok);
  const sum = (k) => ok.reduce((a, e) => a + (e[k] || 0), 0);
  const avg = ok.length ? Math.round(ok.reduce((a, e) => a + e.latency_ms, 0) / ok.length) : 0;
  const k = (v, l) => `<div class="kpi"><div class="v text-cyan-300">${v}</div><div class="l">${l}</div></div>`;
  $("#token-usage").innerHTML = k(calls.length, "LLM calls (session)") + k(sum("prompt_tokens").toLocaleString(), "Prompt tokens") +
    k(sum("completion_tokens").toLocaleString(), "Completion tokens") + k(avg + " ms", "Avg latency");
  $("#routes").innerHTML = `<tr><th>Task</th><th>Model routing order (fallback on quota / error)</th></tr>` +
    Object.entries(st.routes || {}).map(([task, models]) => `<tr><td class="font-mono text-[12px]">${esc(task)}</td>
      <td class="text-[12px]">${models.map((m, i) => `<span class="${i ? "text-slate-500" : "text-emerald-300"}">${esc(SHORT[m] || m)}</span>`).join(' <span class="text-slate-600">→</span> ')}</td></tr>`).join("");
}

function auditRow(e) {
  const map = {
    policy: [e.principal, e.tool, e.effect, e.effect === "ALLOW" ? "b-emerald" : "b-rose"],
    tool_call: [e.principal, e.tool, "EXECUTED", "b-slate"],
    llm_call: ["llm-gateway", `${e.purpose} → ${SHORT[e.model] || e.model}`, e.ok ? "OK" : "ERROR", e.ok ? "b-cyan" : "b-rose"],
    guardrail: ["guardrail", e.type, e.type === "pii_masked" ? "MASKED" : "BLOCKED", "b-amber"],
    human_approval: [e.officer, e.tool, "APPROVED (HITL)", "b-purple"],
    judge: ["judge-agent", "fact-check STR", e.passed ? "PASS" : "REVISE", e.passed ? "b-emerald" : "b-amber"],
    memory: ["agentbase-memory", e.op, e.ok ? "OK" : "ERROR", e.ok ? "b-cyan" : "b-rose"],
    embedding: ["llm-gateway", "embed → bge-m3", e.ok ? "OK" : "ERROR", "b-cyan"],
    rate_limit: ["llm-gateway", `rate-limit ${e.action}`, "THROTTLED", "b-amber"],
    case_start: ["orchestrator", "case opened", "—", "b-slate"],
    case_end: ["orchestrator", `case closed · ${e.status}`, "—", "b-slate"],
    case_cleared: ["orchestrator", "false positive closure", "CLEARED", "b-emerald"],
    honeypot: ["decoy-agent", `honeypot (${e.mode})`, `${e.extracted} acct exposed`, "b-amber"],
    arena: ["red-arena", `engagement ${e.difficulty || ""}`, e.recall !== undefined ? `recall ${(e.recall * 100).toFixed(0)}%` : "—", "b-rose"],
  }[e.kind] || ["system", e.kind, "—", "b-slate"];
  const lat = e.latency_ms ?? e.ms;
  return `<tr><td class="whitespace-nowrap font-mono text-[11px] text-slate-500">${esc((e.ts || "").replace("T", " "))}</td>
    <td class="font-mono text-[11.5px]">${esc(map[0] || "—")}</td><td class="text-[12px]">${esc(map[1] || "—")}${e.case_id ? `<div class="font-mono text-[10px] text-slate-600">${esc(e.case_id)}</div>` : ""}</td>
    <td><span class="badge ${map[3]}">${esc(map[2])}</span></td><td class="font-mono text-[11.5px]">${lat !== undefined && lat !== null ? lat + " ms" : "—"}</td></tr>`;
}

function renderAudit(events) {
  $("#audit").innerHTML = `<tr><th>Timestamp</th><th>Actor</th><th>Tool / Action</th><th>Policy / Result</th><th>Latency</th></tr>` +
    (events.length ? events.slice().reverse().slice(0, 200).map(auditRow).join("") : `<tr><td colspan="5" class="text-slate-500">No events yet — run an investigation.</td></tr>`);
}

function renderPolicy() {
  const pg = state.meta.policy_group;
  $("#pg-name").textContent = pg.name;
  $("#policy").innerHTML = `<tr><th>#</th><th>Principal</th><th>Tool</th><th>Effect</th></tr>` + pg.statements.map((s, i) =>
    `<tr><td class="font-mono">${i + 1}</td><td class="font-mono text-[11.5px]">${esc(s.principal)}</td><td class="font-mono text-[11.5px]">${esc(s.tool)}</td>
     <td><span class="badge ${s.effect === "ALLOW" ? "b-emerald" : "b-rose"}">${s.effect}</span></td></tr>`).join("") +
    `<tr><td colspan="4" class="text-[11.5px] text-slate-500">First match wins. The agent may only read and draft; delay (Art. 44), STR filing (Art. 26) and freezing (Art. 45) require a human officer.</td></tr>`;
}

function renderArchitecture() {
  const box = (icon, title, body, color) => `<div class="rounded-xl border border-slate-800/80 bg-slate-950/50 p-3"><div class="mb-1 flex items-center gap-2 text-[12px] font-semibold ${color}"><i data-lucide="${icon}" class="h-4 w-4"></i>${title}</div><div class="text-[11.5px] leading-relaxed text-slate-400">${body}</div></div>`;
  $("#architecture").innerHTML = `
    <div class="grid gap-3 lg:grid-cols-4">
      ${box("monitor", "Analyst console", "Incognito-safe web UI + <span class='font-mono'>POST /invocations</span> (AgentBase SDK contract).", "text-slate-200")}
      ${box("container", "AgentBase Runtime", "Custom Agent container on GreenNode, image in AgentBase Container Registry, IAM identity auto-injected.", "text-emerald-300")}
      ${box("workflow", "LangGraph agents", "Guardrail → Intel → Ring Hunter → Investigator → Judge → Policy → Memory; false positives branch to explained closure.", "text-cyan-300")}
      ${box("lock-keyhole", "Policy Gateway", "First-match-wins policy group; legal actions DENY for the agent, ALLOW only for the AML officer role.", "text-rose-300")}
      ${box("cpu", "GreenNode MaaS", "Task-routed Qwen 3.8 Flash / Gemma 4 / GLM 5.3 Flash / GLM 5.2 with per-model RPM guard; bge-m3 RAG over AML law.", "text-cyan-300")}
      ${box("database", "AgentBase Memory", "Long-term “ring fingerprints” (accounts, devices) — recognises a known ring resurfacing across cases.", "text-purple-300")}
      ${box("binary", "Risk engine", "21 behavioural features mapped to Art. 27–28; monotonic gradient boosting; Shapley attribution.", "text-amber-300")}
      ${box("swords", "Red Arena", "LLM adversary plans evasive campaigns; simulator executes; defender self-evolves on misses.", "text-rose-300")}
    </div>
    <div class="mt-3 flex flex-wrap gap-2 text-[11px]">
      <span class="badge b-emerald">Image deployed on GreenNode AgentBase</span><span class="badge b-emerald">GreenNode MaaS models only</span>
      <span class="badge b-emerald">Per-user RPM limits enforced</span><span class="badge b-emerald">100% synthetic data</span><span class="badge b-emerald">No secrets in image or repo</span>
    </div>`;
  icons();
}
