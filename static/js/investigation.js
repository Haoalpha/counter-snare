// TAB 1 — Investigation Pipeline: 4-stage interactive stepper
import { $, $$, api, busy, esc, icons, pct, state, stepEn, toast, vnd, vndShort, ROLE, TYPOLOGY_EN, FEATURE_EN, TOOL_EN } from "./core.js";
import { openInterceptor } from "./policy.js";

const STAGES = [
  { n: 1, title: "STAGE 01: THREAT INGESTION & ZERO-TRUST GUARDRAILS", sub: "Scam intel · PII masking · injection defence" },
  { n: 2, title: "STAGE 02: MULE RING HUNTER & FORENSIC GRAPH", sub: "Graph expansion · GBM scoring · XAI" },
  { n: 3, title: "STAGE 03: FORENSIC EVIDENCE & STR SYNTHESIS", sub: "Evidence vault · STR draft · Judge" },
  { n: 4, title: "STAGE 04: POLICY GATE & HUMAN-IN-THE-LOOP (HITL)", sub: "Policy interceptor · officer sign-off" },
];
let network = null;
let graphDrawn = false;
let selectedPreset = null;
let selectedCampaign = null; // kịch bản ẩn (mô phỏng) cho ScamBot khi chạy Honeypot

export function initInvestigation() {
  renderStepper();
  const meta = state.meta;
  const presets = meta.presets || [];
  $("#presets").innerHTML = presets.map((p, i) =>
    `<button class="chip-btn" data-preset="${i}"><i data-lucide="${p.id === "P3" ? "badge-check" : p.honeypot ? "fish" : "flame"}" class="h-3.5 w-3.5"></i>Preset ${i + 1}: ${esc(p.label)}</button>`).join("");
  $$("[data-preset]").forEach((b) => b.onclick = () => choosePreset(+b.dataset.preset));
  $("#more-scenarios").innerHTML = `<option value="">— select —</option>` + meta.samples.map((s, i) =>
    `<option value="${i}">#${i + 1} ${esc(TYPOLOGY_EN[s.typology] || s.typology)}${i === 0 ? " (with injection)" : ""}</option>`).join("");
  $("#more-scenarios").onchange = (e) => {
    if (e.target.value === "") return;
    const s = meta.samples[e.target.value];
    $("#threat-input").value = s.text; selectedPreset = null; selectedCampaign = s.campaign_id;
    $$("[data-preset]").forEach((x) => x.classList.remove("selected"));
  };
  $("#threat-input").addEventListener("input", () => { selectedCampaign = null; });
  if (presets.length) choosePreset(1); else $("#threat-input").value = meta.samples[0].text;

  $("#btn-execute").onclick = execute;
  $("#btn-honeypot").onclick = honeypot;
  $$(".next-stage").forEach((b) => b.onclick = () => goStage(+b.dataset.go));
  $("#act-export").onclick = exportDossier;
  $("#act-dismiss").onclick = dismiss;
  $$("[data-danger]").forEach((b) => b.onclick = () => danger(b.dataset.danger));
  renderPipelinePlaceholder();
  const q = new URLSearchParams(location.search).get("case");
  if (q) api("/api/case/" + q).then(render).catch(() => {});
}

function choosePreset(i) {
  selectedPreset = i;
  const p = state.meta.presets[i];
  selectedCampaign = p.campaign_id || state.meta.samples.find((s) => s.text === p.text)?.campaign_id || null;
  $("#threat-input").value = p.text;
  $("#btn-honeypot").classList.toggle("honeypot-hint", !!p.honeypot);
  $$("[data-preset]").forEach((x) => x.classList.toggle("selected", +x.dataset.preset === i));
  $("#more-scenarios").value = "";
}

// ---------------- stepper ----------------
function renderStepper() {
  $("#stepper").innerHTML = STAGES.map((s) => {
    const cls = s.n === state.stage ? "active" : s.n < state.stage || s.n <= state.maxStage && s.n !== state.stage ? "done" : "";
    const locked = s.n > state.maxStage ? "locked" : "";
    return `<li><button class="step ${cls} ${locked}" data-step="${s.n}" ${locked ? 'aria-disabled="true"' : ""}>
      <span class="num">0${s.n}</span><span><span class="title block">${esc(s.title.replace(/^STAGE 0\d: /, ""))}</span><span class="sub block">${esc(s.sub)}</span></span></button></li>`;
  }).join("");
  $$("[data-step]").forEach((b) => b.onclick = () => { const n = +b.dataset.step; if (n <= state.maxStage) goStage(n); });
}

export function goStage(n) {
  if (n > state.maxStage) return;
  state.stage = n;
  $$(".stage").forEach((el) => el.classList.toggle("hidden", +el.dataset.stage !== n));
  renderStepper();
  if (n === 2 && state.caseData && state.caseData.ring && !graphDrawn) drawGraph(state.caseData.ring);
  if (n === 2 && network) setTimeout(() => network.fit({ animation: false }), 50);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------- stage 1 ----------------
function renderPipelinePlaceholder(running = false) {
  const steps = ["Zero-Trust Guardrails", "Intel Agent · seed extraction", "Mule Ring Hunter · graph + GBM", "Investigator Agent · STR synthesis",
    "Agent-as-a-Judge · fact-check", "Policy Gateway · action proposal", "AgentBase Memory · ring fingerprint"];
  $("#pipeline").innerHTML = steps.map((s) => `<li class="pipe-item">${running ? '<span class="spinner"></span>' : '<i data-lucide="circle-dashed" class="h-4 w-4 text-slate-600"></i>'}
    <span class="${running ? "text-slate-300" : "text-slate-500"}">${s}</span><span class="ms">${running ? "running" : "idle"}</span></li>`).join("");
  $("#pipeline-total").textContent = "";
  icons();
}

async function execute() {
  const text = $("#threat-input").value.trim();
  if (!text) return toast("Paste a scam message or alert first.", "error");
  const b = $("#btn-execute");
  busy(b, true, "Agents running on GreenNode…");
  renderPipelinePlaceholder(true);
  try { render(await api("/api/investigate", { text })); }
  catch (e) { toast(e.message, "error"); renderPipelinePlaceholder(); }
  finally { busy(b, false); }
}

async function honeypot() {
  const b = $("#btn-honeypot");
  busy(b, true, "Decoy agent engaging scammer…");
  try {
    const text = $("#threat-input").value.trim();
    if (!text) { toast("Paste the scammer's opening message first.", "error"); return; }
    const h = await api("/api/honeypot", { text, campaign_id: selectedCampaign });
    $("#btn-honeypot").classList.remove("honeypot-hint");
    const p = $("#honeypot-panel");
    p.classList.remove("hidden");
    p.innerHTML = `<div class="rounded-xl border border-slate-800/80 bg-slate-950/50 p-3">
      <div class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400"><i data-lucide="fish" class="h-4 w-4 text-amber-400"></i>
        Honeypot Decoy Agent · "Grandma Tu" persona <span class="badge b-slate ml-auto">${h.mode === "llm" ? "2 LLMs live on GreenNode MaaS" : "scripted fallback"}</span></div>
      <div class="flex max-h-72 flex-col gap-2 overflow-y-auto">${h.transcript.map((t) => `<div class="bubble ${t.who}"><span class="who">${t.who === "batu" ? "DECOY · GRANDMA TU (AI)" : "SCAMMER · SIMULATED"}</span>${esc(t.text)}</div>`).join("")}</div>
      ${h.extracted_accounts.length ? `<div class="mt-3 flex flex-wrap items-center gap-2"><span class="badge b-emerald"><i data-lucide="target" class="h-3 w-3"></i>Mule account exposed</span>
        <span class="font-mono text-sm text-white">${h.extracted_accounts.map(esc).join(", ")}</span>
        <button id="btn-hp-investigate" class="btn btn-primary ml-auto py-1.5 text-xs"><i data-lucide="play" class="h-3.5 w-3.5"></i>Investigate this transcript</button></div>`
        : `<div class="mt-3 badge b-rose">No account exposed yet</div>`}
      ${h.opening_had_account ? `<p class="mt-2 text-[11.5px] text-amber-300">This message already contained a receiving account — Execute Analysis can investigate it directly; the decoy is most useful when the scammer has not revealed the account yet.</p>` : ""}
      <p class="mt-2 text-[11px] text-slate-500">Simulation only. In production the default mode is passive (customers forward scam chats); active baiting runs only under the SBV – Ministry of Public Security coordination framework.</p></div>`;
    icons();
    const go = $("#btn-hp-investigate");
    if (go) go.onclick = () => { $("#threat-input").value = h.scam_text; execute(); };
  } catch (e) { toast(e.message, "error"); }
  finally { busy(b, false); }
}

function render(c) {
  state.caseData = c;
  graphDrawn = false;
  const g = c.guard || {};
  const inj = g.injection || [];
  const pii = g.pii_masked || [];
  $("#guardrails").innerHTML = `
    <div class="badge b-emerald w-full justify-start py-1.5"><i data-lucide="check" class="h-3.5 w-3.5"></i>PII Masking Active: Citizen ID / Phone Anonymized${pii.length ? ` (${pii.length} masked)` : ""}</div>
    <div class="badge b-emerald w-full justify-start py-1.5"><i data-lucide="check" class="h-3.5 w-3.5"></i>Anti-Prompt Injection: Enforced</div>
    <div class="badge b-emerald w-full justify-start py-1.5"><i data-lucide="check" class="h-3.5 w-3.5"></i>Regex-first extraction: LLM cannot invent accounts</div>
    ${inj.length ? `<div class="mt-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-[12px] text-rose-200 fade-in">
      <div class="mb-1 flex items-center gap-1.5 font-semibold text-rose-300"><i data-lucide="shield-alert" class="h-4 w-4"></i>Injection attempt neutralised</div>
      <span class="font-mono text-[11px]">${inj.slice(0, 4).map(esc).join(" · ")}</span>
      <div class="mt-1 text-rose-300/80">Isolated as untrusted data — risk scores are computed by the model, never by the LLM.</div></div>`
      : `<div class="text-[12px] text-slate-500">No injection pattern detected in this message.</div>`}`;

  const it = c.intel || {};
  const seeds = it.accounts_in_bank || [];
  $("#seed-card").innerHTML = seeds.length ? `
    ${seeds.map((a) => `<div class="mb-2 rounded-lg border border-rose-500/30 bg-rose-500/5 p-2.5">
      <div class="text-[10px] font-semibold uppercase tracking-wider text-rose-300">Extracted Seed ${c.status === "CLEARED" ? "Account" : "Mule"}</div>
      <div class="font-mono text-lg font-semibold text-white">${esc(a)} <span class="text-sm text-slate-400">(${esc((c.ring?.nodes.find((n) => n.id === a) || {}).bank || "NHX")})</span></div></div>`).join("")}
    <div class="space-y-1 text-[12px]">
      <div><span class="text-slate-500">Typology:</span> <span class="text-slate-200">${esc(TYPOLOGY_EN[it.typology] || it.typology)}</span> ${it.llm ? '<span class="badge b-cyan ml-1">LLM · GreenNode MaaS</span>' : '<span class="badge b-slate ml-1">rule-based</span>'}</div>
      ${it.impersonated_entity ? `<div><span class="text-slate-500">Impersonating:</span> ${esc(it.impersonated_entity)}</div>` : ""}
      ${(it.pressure_tactics || []).length ? `<div class="flex flex-wrap gap-1 pt-1">${it.pressure_tactics.slice(0, 4).map((x) => `<span class="badge b-amber">${esc(x)}</span>`).join("")}</div>` : ""}
      ${it.accounts_unknown && it.accounts_unknown.length ? `<div class="text-slate-500">Outside our bank: <span class="font-mono">${it.accounts_unknown.map(esc).join(", ")}</span></div>` : ""}
    </div>` : `<div class="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 fade-in">
      <div class="flex items-center gap-2 text-[12px] font-semibold text-amber-300"><i data-lucide="search-x" class="h-4 w-4"></i>No receiving account in this message yet</div>
      <p class="mt-1 text-[12px] text-slate-300">${it.accounts_unknown && it.accounts_unknown.length
        ? `Account(s) found are outside our bank: <span class="font-mono">${it.accounts_unknown.map(esc).join(", ")}</span>. Share with the receiving bank via SIMO.`
        : "The scammer has only made first contact. Deploy the decoy agent to keep them talking until they reveal the mule account — then investigate the whole ring."}</p>
      <div class="mt-1 text-[11.5px] text-slate-500">Typology so far: ${esc(TYPOLOGY_EN[it.typology] || it.typology)}</div>
      ${it.accounts_unknown && it.accounts_unknown.length ? "" : `<button id="btn-suggest-honeypot" class="btn btn-ghost mt-2 py-1.5 text-xs"><i data-lucide="fish" class="h-3.5 w-3.5"></i>Deploy Honeypot Decoy Agent</button>`}
    </div>`;
  const sh = $("#btn-suggest-honeypot");
  if (sh) sh.onclick = honeypot;

  $("#pipeline").innerHTML = (c.timeline || []).map((t) => `<li class="pipe-item fade-in"><i data-lucide="check-circle-2" class="h-4 w-4 text-emerald-400"></i>
    <span class="text-slate-200">${esc(stepEn(t.step))}</span><span class="ms">${t.ms} ms</span></li>`).join("");
  $("#pipeline-total").textContent = c.total_ms ? `${(c.total_ms / 1000).toFixed(1)} s end-to-end` : "";

  state.maxStage = seeds.length ? 4 : 1;
  $$(".next-stage[data-go='2']").forEach((b) => b.disabled = !seeds.length);
  if (c.ring) { renderKpis(c); renderLedger(c); renderStage3(c); renderStage4(c); }
  renderStepper();
  icons();
  if (seeds.length) toast(c.status === "CLEARED" ? "Analysis complete: false positive — no mule ring." : `Analysis complete: ${c.ring.summary.n_mules} mule accounts mapped. Proceed to Stage 02.`);
  else { toast("No receiving account yet — deploy the Honeypot Decoy Agent to make the scammer reveal it."); $("#btn-honeypot").classList.add("honeypot-hint"); }
}

// ---------------- stage 2 ----------------
function renderKpis(c) {
  const s = c.ring.summary;
  const k = (v, l, color = "text-white") => `<div class="kpi fade-in"><div class="v ${color}">${v}</div><div class="l">${l}</div></div>`;
  $("#kpis").innerHTML = c.status === "CLEARED"
    ? k("0", "Mule accounts", "text-emerald-400") + k("CLEARED", "Verdict", "text-emerald-400") + k(((c.total_ms || 0) / 1000).toFixed(1) + "s", "Time to verdict")
    : k(s.n_mules, "Mule accounts mapped", "text-rose-400") + k(s.n_victims, `Victims (${s.n_victims_ato} compromised)`, "text-sky-400")
      + k(vndShort(s.victim_loss), "Victim funds traced", "text-amber-400") + k(vndShort(s.est_remaining), "Still in ring — recoverable", "text-emerald-400")
      + k(((c.total_ms || 0) / 1000).toFixed(1) + "s", "Seed → dossier (manual: 1–2 days)")
      + k((c.simo || []).length, "Accounts already on SIMO", "text-rose-300") + k((c.memory_hits || []).length, "Known-ring matches (Memory)", "text-cyan-400");
  $("#legend").innerHTML = ["collector", "layer", "cashout", "victim", "victim_ato", "sink"].map((r) =>
    `<span class="flex items-center gap-1.5"><span class="inline-block h-2.5 w-2.5 rounded-sm" style="background:${ROLE[r].color}"></span>${ROLE[r].en} <span class="text-slate-600">(${ROLE[r].shape})</span></span>`).join("")
    + `<span class="text-slate-500">– – shared device</span>`;
}

function drawGraph(ring) {
  const nodes = ring.nodes.map((n) => {
    const R = ROLE[n.role] || ROLE.related;
    return {
      id: n.id, label: n.role === "sink" ? n.holder_name.slice(0, 22) : n.id.slice(-6) + (n.seed ? " ★" : ""),
      shape: R.shape, size: n.role.startsWith("victim") ? 9 : n.role === "sink" ? 14 : n.role === "collector" ? 20 : 15,
      color: { background: R.color, border: n.seed ? "#ffffff" : "#0b0f19", highlight: { background: R.color, border: "#f59e0b" } },
      borderWidth: n.seed ? 3 : 1, font: { color: "#cbd5e1", size: 11, face: "Fira Code" },
      title: `${n.id} · ${R.en} · risk ${pct(n.score)}`,
    };
  });
  const edges = ring.edges.map((e, i) => e.type === "device"
    ? { id: "d" + i, from: e.src, to: e.dst, dashes: [4, 4], color: { color: "rgba(148,163,184,0.7)" }, width: 1, title: "Shared device " + e.device }
    : { id: "e" + i, from: e.src, to: e.dst, arrows: { to: { enabled: true, scaleFactor: 0.5 } }, width: Math.min(7, 1 + Math.log10(1 + e.amount / 1e6) * 1.8),
        color: { color: "rgba(144,164,174,0.6)", highlight: "#f59e0b" }, title: `${vnd(e.amount)} · ${e.count} tx` });
  network = new vis.Network($("#graph"), { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, {
    physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -55, springLength: 95 }, stabilization: { iterations: 220 } },
    interaction: { hover: true, tooltipDelay: 120 },
  });
  network.once("stabilizationIterationsDone", () => { network.fit({ animation: false }); network.setOptions({ physics: { enabled: false } }); });
  network.on("click", (p) => { if (p.nodes.length) showXai(p.nodes[0]); });
  graphDrawn = true;
  const top = ring.nodes.filter((n) => n.role === "collector").sort((a, b) => b.score - a.score)[0] || ring.nodes.find((n) => n.seed);
  if (top) { showXai(top.id); network.selectNodes([top.id]); }
}

async function showXai(id) {
  const n = state.caseData.ring.nodes.find((x) => x.id === id) || { role: "related" };
  const box = $("#xai");
  box.innerHTML = `<div class="flex items-center gap-2 text-slate-500"><span class="spinner"></span>Computing Shapley attribution…</div>`;
  const d = await api("/api/account/" + id);
  const r = d.risk, p = d.profile;
  const R = ROLE[n.role] || ROLE.related;
  const color = r.score >= 0.8 ? "#f43f5e" : r.score >= 0.5 ? "#f59e0b" : r.score >= 0.2 ? "#fbbf24" : "#34d399";
  const maxImp = Math.max(0.01, ...r.contributions.map((x) => Math.abs(x.impact)));
  box.innerHTML = `<div class="fade-in">
    <div class="flex items-start justify-between gap-3">
      <div><div class="font-mono text-base font-semibold text-white">${esc(id)}</div>
        <div class="mt-1 flex flex-wrap gap-1.5"><span class="badge ${R.badge}">${R.en}</span><span class="badge b-slate">${esc(p.bank)}</span><span class="badge b-slate">${esc(p.kyc_channel)} · ${p.account_age_days}d old</span></div>
        <div class="mt-1 text-[12px] text-slate-500">${esc(p.holder_name)} · ${p.age}y · declared income ${vnd(p.declared_income)}/mo</div></div>
      <div class="text-right"><div class="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Monotonic GBM Risk Score</div>
        <div class="font-mono text-4xl font-bold" style="color:${color}">${pct(r.score)}</div><div class="text-[11px] text-slate-500">${esc(r.band)}</div></div>
    </div>
    <div class="mt-4 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Feature attribution · Shapley (Monte-Carlo) vs. typical customer</div>
    <div class="mt-2 space-y-2.5">${r.contributions.length ? r.contributions.map((x) => `
      <div><div class="flex justify-between gap-2 text-[12px]"><span class="text-slate-300">${esc(FEATURE_EN[x.feature] || x.feature)}
        <span class="font-mono text-[10.5px] text-slate-500">${fmtVal(x.feature, x.value)} vs ${fmtVal(x.feature, x.normal_median)}</span></span>
        <span class="font-mono font-semibold ${x.impact >= 0 ? "text-rose-300" : "text-emerald-300"}">${x.impact >= 0 ? "+" : ""}${(x.impact * 100).toFixed(1)}%</span></div>
        <div class="bar-track mt-1"><div class="bar-fill" style="width:${Math.abs(x.impact) / maxImp * 100}%;background:${x.impact >= 0 ? "linear-gradient(90deg,#f59e0b,#f43f5e)" : "#34d399"}"></div></div></div>`).join("")
      : `<div class="placeholder">Low-risk account — no material risk drivers.</div>`}</div>
    ${r.red_flags.length ? `<div class="mt-4 rounded-lg border border-slate-800/80 bg-slate-950/50 p-3"><div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-300">Suspicious-activity indicators · Căn cứ Điều 27, 28 Luật PCRT 2022</div>
      <ul class="space-y-1 text-[12px] text-slate-300">${r.red_flags.map((f) => `<li class="flex gap-2"><i data-lucide="alert-triangle" class="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400"></i><span>${esc(f.text)} <span class="text-slate-500">— ${esc(f.legal)}</span></span></li>`).join("")}</ul></div>` : ""}
    ${r.mitigating.length ? `<div class="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><div class="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">Mitigating factors</div>
      <ul class="space-y-1 text-[12px] text-slate-300">${r.mitigating.map((f) => `<li>${esc(f.text)}</li>`).join("")}</ul></div>` : ""}
  </div>`;
  icons();
}

function fmtVal(f, v) {
  if (["fast_out_ratio", "foreign_ip_ratio", "night_ratio", "cashout_ratio", "pass_through", "same_holder_out_ratio", "small_in_ratio", "qr_in_ratio"].includes(f)) return pct(v);
  if (f === "income_ratio") return v.toFixed(0) + "×";
  if (f === "median_dwell_min") return v >= 10000 ? "n/a" : v.toFixed(0) + "m";
  if (f === "ekyc" || f === "is_business") return v ? "yes" : "no";
  if (f === "log_sum_in") return vndShort(Math.expm1(v));
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function renderLedger(c) {
  const rows = [...c.ring.nodes].sort((a, b) => b.score - a.score);
  $("#ledger").innerHTML = `<tr><th>Account</th><th>Role</th><th>Bank</th><th>Holder (masked)</th><th>Account age</th><th>Risk</th><th>Hop</th></tr>` +
    rows.map((n) => { const R = ROLE[n.role] || ROLE.related; return `<tr class="cursor-pointer" data-acct="${esc(n.id)}"><td class="font-mono">${esc(n.id)}${n.seed ? ' <span class="text-amber-400">★ seed</span>' : ""}</td>
      <td><span class="badge ${R.badge}">${R.en}</span></td><td>${esc(n.bank)}</td><td>${esc(n.holder_masked)}</td><td>${n.account_age_days}d</td>
      <td class="font-mono ${n.score >= 0.5 ? "text-rose-300" : "text-emerald-300"}">${pct(n.score)}</td><td class="font-mono">${n.hop}</td></tr>`; }).join("");
  $$("#ledger [data-acct]").forEach((tr) => tr.onclick = () => { showXai(tr.dataset.acct); if (network) network.selectNodes([tr.dataset.acct]); });
}

// ---------------- stage 3 ----------------
function renderStage3(c) {
  if (c.status === "CLEARED") {
    const cl = c.clearance;
    $("#judge-banner").innerHTML = `<div class="glass flex items-center gap-3 border-emerald-500/40"><i data-lucide="badge-check" class="h-6 w-6 text-emerald-400"></i>
      <div><div class="font-semibold text-emerald-300">No STR required — alert closed as false positive</div><div class="text-[12px] text-slate-400">${esc(cl.note)}</div></div></div>`;
    $("#vault").innerHTML = (c.evidence || []).map(evCard).join("") || `<div class="placeholder">No incriminating evidence generated.</div>`;
    $("#dossier").innerHTML = `<div class="dossier"><h2>BIÊN BẢN RÀ SOÁT CẢNH BÁO (DƯƠNG TÍNH GIẢ)</h2><div class="sub">Mã vụ việc ${esc(c.case_id)}</div>
      <h4>Kết luận</h4><p>${esc(cl.verdict)}. ${esc(cl.note)}</p>
      <h4>Tài khoản được rà soát</h4>${cl.accounts.map((a) => `<p><span class="mono">${esc(a.account_id)}</span> – ${esc(a.holder)} (${esc(a.segment)}), điểm rủi ro ${pct(a.score)}.</p>
      <ul>${a.mitigating.map((m) => `<li>${esc(m.text)} <i>(${esc(m.legal)})</i></li>`).join("")}</ul>`).join("")}</div>`;
    $("#str-meta").textContent = "closure memo";
    return;
  }
  const j = c.judge;
  const verified = j.checked.filter((x) => x.ok).length;
  const rep = (j.repaired || []).length;
  const sc = j.rubric && j.rubric.scores ? Object.values(j.rubric.scores).filter((v) => typeof v === "number") : [];
  const avg = sc.length ? (sc.reduce((a, b) => a + b, 0) / sc.length).toFixed(1) : null;
  $("#judge-banner").innerHTML = `<div class="glass flex flex-wrap items-center gap-3 border-emerald-500/40 fade-in">
    <i data-lucide="shield-check" class="h-6 w-6 text-emerald-400"></i>
    <div class="min-w-0 flex-1"><div class="font-semibold text-emerald-300">✓ Agent-as-a-Judge Certified: 100% of final claims traceable to the Evidence Vault · 0 unsupported claims</div>
      <div class="text-[12px] text-slate-400">${verified}/${j.checked.length} draft claims passed the deterministic number-by-number fact-check${rep ? ` · ${rep} auto-repaired from ledger data` : ""}${avg ? ` · rubric ${avg}/5` : ""}${j.revisions ? ` · ${j.revisions} LLM rewrite` : ""}</div></div>
    <span class="badge b-cyan">Draft by GreenNode MaaS · ${esc(c.str.mode === "llm" ? "LLM" : "template")}</span></div>`;
  $("#vault").innerHTML = c.evidence.map(evCard).join("");
  const evm = Object.fromEntries(c.evidence.map((e) => [e.id, e.text]));
  const tag = (ids) => (ids || []).map((id) => `<span class="ev-tag ${evm[id] ? "" : "invalid"}" data-ev="${esc(id)}" title="${esc(evm[id] || "missing")}">[${esc(id)}]</span>`).join("");
  const inline = (t) => esc(t).replace(/\[?(EV-\d+)\]?/g, (m, id) => `<span class="ev-tag ${evm[id] ? "" : "invalid"}" data-ev="${id}" title="${esc(evm[id] || "")}">[${id}]</span>`);
  const s = c.str;
  $("#str-meta").textContent = `${s.case_id} · ${s.created}`;
  $("#dossier").innerHTML = `<div class="dossier fade-in">
    <h2>${esc(s.title)}</h2><div class="sub">Mã vụ việc ${esc(s.case_id)} · lập ${esc(s.created)} · Mẫu tham khảo theo Luật PCRT 2022</div>
    <h4>1. Đối tượng báo cáo</h4><p>${esc(s.reporting_entity)}<br>Căn cứ: ${esc(s.basis)}<br>Hạn nộp: <b>${esc(s.deadline)}</b></p>
    <h4>2. Tóm tắt</h4><p>${inline(s.tom_tat)}</p>
    <h4>3. Tài khoản liên quan</h4><table><tr><th>Số tài khoản</th><th>NH</th><th>Chủ TK (đã che)</th><th>Vai trò</th><th>Mở TK</th><th>Rủi ro</th></tr>
      ${s.accounts.map((a) => `<tr><td class="mono">${esc(a.account_id)}</td><td>${esc(a.bank)}</td><td>${esc(a.holder)}</td><td>${esc({ collector: "Gom tiền", layer: "Trung chuyển", cashout: "Rút/chuyển ra" }[a.role] || a.role)}</td><td>${esc(a.open_date)} (${esc(a.kyc)})</td><td>${pct(a.score)}</td></tr>`).join("")}</table>
    <p>Tổng tiền nạn nhân chuyển vào: <b>${esc(s.total_victim_loss)}</b> ${tag(["EV-02"])} · Ước còn trong đường dây: <b>${esc(s.est_remaining)}</b> ${tag(["EV-02"])}</p>
    <h4>4. Nhận định thủ đoạn</h4><p>${inline(s.nhan_dinh_thu_doan)}</p>
    <h4>5. Dấu hiệu đáng ngờ & bằng chứng</h4><ol class="list-decimal pl-5">${(s.dau_hieu || []).map((d) => `<li>${esc(d.noi_dung)} ${tag(d.ev)} ${d.can_cu ? `<span style="color:#64748b">[${esc(d.can_cu)}]</span>` : ""}</li>`).join("")}</ol>
    <h4>6. Đề xuất</h4><ul class="list-disc pl-5">${(s.de_xuat || []).map((x) => `<li>${inline(x)}</li>`).join("")}</ul></div>`;
  $$("#dossier [data-ev]").forEach((t) => t.onclick = () => flashEvidence(t.dataset.ev));
}

function evCard(e) {
  return `<div class="ev-card" id="vault-${esc(e.id)}"><div class="flex items-center gap-2"><span class="ev-tag">${esc(e.id)}</span>
    <span class="text-[10.5px] uppercase tracking-wider text-slate-500">${esc(e.legal || "ledger fact")}</span></div>
    <div class="mt-1.5 text-[12.5px] leading-relaxed text-slate-300">${esc(e.text)}</div>
    ${e.tx_ids && e.tx_ids.length ? `<div class="mt-1.5 font-mono text-[10.5px] text-slate-500">tx: ${e.tx_ids.slice(0, 4).map(esc).join(" · ")}</div>` : ""}</div>`;
}

function flashEvidence(id) {
  const el = document.getElementById("vault-" + id);
  if (!el) return toast(`${id} is not in the Evidence Vault`, "error");
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
}

// ---------------- stage 4 ----------------
export function renderStage4(c) {
  const acts = c.actions || [];
  $("#action-register").innerHTML = `<tr><th>ID</th><th>Action</th><th>Legal basis</th><th>Deadline</th><th>Status</th></tr>` +
    acts.map((a) => `<tr><td class="font-mono">${esc(a.id)}</td><td>${esc((TOOL_EN[a.tool] || {}).label || a.title)}
      ${a.agent_attempt && a.agent_attempt !== "ALLOW" ? '<div class="mt-0.5 text-[11px] text-rose-300">Agent self-attempt → DENY (policy)</div>' : ""}</td>
      <td class="text-[12px] text-slate-400">${esc(a.legal)}</td><td class="font-mono">${esc(a.deadline || "—")}</td>
      <td><span class="badge ${/DUYỆT bởi/.test(a.status) ? "b-emerald" : /CHỜ|CẦN/.test(a.status) ? "b-amber" : "b-slate"}">${esc(englishStatus(a.status))}</span></td></tr>`).join("");
  const isCleared = c.status === "CLEARED";
  $("#act-dismiss").className = "btn " + (isCleared ? "btn-primary" : "btn-muted");
  $("#act-export").className = "btn " + (isCleared ? "btn-muted" : "btn-primary");
}

function englishStatus(s) {
  if (/ĐÃ DUYỆT bởi/.test(s)) return "APPROVED · " + s.replace(/^ĐÃ DUYỆT bởi\s*/, "").replace(" – đã nộp NHNN (mô phỏng)", " · filed (simulated)");
  return { "CHỜ CHUYÊN VIÊN DUYỆT": "PENDING OFFICER APPROVAL", "KHUYẾN NGHỊ": "RECOMMENDED", "CẦN QUYẾT ĐỊNH CƠ QUAN CÓ THẨM QUYỀN": "REQUIRES AUTHORITY DECISION" }[s] || s;
}

async function danger(tool) {
  const c = state.caseData;
  if (!c || !c.ring) return toast("Run an investigation first.", "error");
  const verdict = await api("/api/agent_try", { case_id: c.case_id, tool });
  openInterceptor(tool, verdict, c, () => renderStage4(state.caseData));
}

function dismiss() {
  const c = state.caseData;
  if (!c) return toast("Run an investigation first.", "error");
  const li = document.createElement("li");
  li.className = "rounded-lg border border-slate-700 bg-slate-900/70 p-2 fade-in";
  li.innerHTML = `<span class="font-mono text-[11px] text-slate-500">${new Date().toLocaleTimeString()}</span> · Case ${esc(c.case_id)} marked <b>${c.status === "CLEARED" ? "false positive (agent recommendation accepted)" : "false positive by analyst — override logged"}</b>`;
  const log = $("#hitl-log"); if (log.querySelector(".placeholder")) log.innerHTML = ""; log.prepend(li);
  toast("Disposition recorded in the HITL ledger.");
}

function exportDossier() {
  const c = state.caseData;
  if (!c || !c.str) return toast("No STR dossier to export for this case.", "error");
  const html = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>${esc(c.str.case_id)} – STR draft</title>
    <style>body{font-family:system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#0f172a;line-height:1.6}
    h2{text-align:center}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #e2e8f0;padding:4px 6px;text-align:left;font-size:13px}
    .ev-tag{font-family:monospace;font-size:11px;background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;border-radius:4px;padding:0 4px}</style></head>
    <body>${$("#dossier").innerHTML}<h4>Phụ lục – Kho bằng chứng</h4><ul>${c.evidence.map((e) => `<li><b>${esc(e.id)}</b>: ${esc(e.text)}</li>`).join("")}</ul>
    <p style="color:#64748b;font-size:12px">Dự thảo do COUNTER-SNARE tạo – cần chuyên viên PCRT rà soát và ký trước khi nộp.</p></body></html>`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  a.download = `${c.str.case_id}_STR_draft.html`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast("STR dossier exported for officer review.");
}
