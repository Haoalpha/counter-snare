// Case Board: KPIs, growing forensic graph + Shapley XAI, evidence vault, STR dossier, legal-action approvals (HITL)
import { $, $$, api, esc, icons, pct, toast, vnd, vndShort, englishStatus, FEATURE_EN, ROLE, TOOL_EN } from "./core.js";

let network = null, nodesDS = null, edgesDS = null, graphKey = "", growTimer = null;
let current = null; // run being shown

// ---------- view model: final result if done, otherwise what the agents have produced so far ----------
export function view(run) {
  if (run.result && run.result.status !== "ERROR") return run.result;
  const p = run.partial || {};
  return { case_id: run.case_id, status: "RUNNING", intel: p.intel, ring: p.ring, evidence: p.evidence, draft: p.draft, actions: p.actions };
}

export function renderBoard(run, { animate = false } = {}) {
  current = run;
  const v = run ? view(run) : null;
  renderKpis(v, run);
  renderGraph(v, animate);
  renderEvidence(v);
  renderStr(v);
  renderActions(run);
  icons();
}

export function showPane(id) {
  $$(".seg button").forEach((b) => b.classList.toggle("active", b.dataset.pane === id));
  $$(".pane").forEach((p) => { p.hidden = p.id !== id; });
  if (id === "pane-network" && network) setTimeout(() => network.fit({ animation: false }), 30);
}

function renderKpis(v, run) {
  const k = (val, l, color = "") => `<div class="kpi"><div class="v" style="${color ? `color:${color}` : ""}">${val}</div><div class="l">${l}</div></div>`;
  const s = v && v.ring ? v.ring.summary : null;
  const secs = run ? (((run.result && run.result.total_ms) || (run.lastTs && run.t0 ? (run.lastTs - run.t0) * 1000 : 0)) / 1000).toFixed(1) + "s" : "—";
  if (v && v.status === "CLEARED") {
    $("#board-kpis").innerHTML = k("0", "Mule accounts", "#047857") + k("FP", "Verdict: false positive", "#047857") + k("0", "STR filed")
      + k("0", "Customer friction") + k(secs, "Time to verdict") + k((v.memory_hits || []).length, "Known-ring matches");
    return;
  }
  $("#board-kpis").innerHTML = s
    ? k(s.n_mules, "Mule accounts", "#BE123C") + k(s.n_victims, `Victims (${s.n_victims_ato} ATO)`, "#0369A1") + k(vndShort(s.victim_loss), "Funds traced", "#A16207")
      + k(vndShort(s.est_remaining), "Still in ring", "#047857") + k(secs, "Seed → dossier") + k((v.simo || []).length + " / " + (v.memory_hits || []).length, "SIMO / memory hits")
    : k("—", "Mule accounts") + k("—", "Victims") + k("—", "Funds traced") + k("—", "Still in ring") + k(secs, "Elapsed") + k("—", "SIMO / memory hits");
}

// ---------- graph ----------
function nodeObj(n) {
  const R = ROLE[n.role] || ROLE.related;
  return {
    id: n.id, label: n.role === "sink" ? String(n.holder_name || "").slice(0, 20) : n.id.slice(-6) + (n.seed ? " ★" : ""),
    shape: R.shape, size: n.role.startsWith("victim") ? 9 : n.role === "sink" ? 13 : n.role === "collector" ? 19 : 14,
    color: { background: R.color, border: n.seed ? "#A16207" : "#ffffff", highlight: { background: R.color, border: "#2A0E19" } },
    borderWidth: n.seed ? 3 : 1.5, font: { color: "#2A0E19", size: 10.5, face: "IBM Plex Mono" },
    title: `${n.id} · ${R.en} · risk ${pct(n.score)} · hop ${n.hop}`,
  };
}
function edgeObj(e, i) {
  return e.type === "device"
    ? { id: "d" + i, from: e.src, to: e.dst, dashes: [4, 4], color: { color: "rgba(123,94,104,0.55)" }, width: 1, title: "Shared device " + (e.device || "") }
    : { id: "e" + i, from: e.src, to: e.dst, arrows: { to: { enabled: true, scaleFactor: 0.45 } }, width: Math.min(3.5, 0.8 + Math.log10(1 + e.amount / 1e6) * 0.9),
        color: { color: "rgba(122,18,56,0.30)", highlight: "#C2185B", hover: "#C2185B" }, title: `${vnd(e.amount)} · ${e.count} tx` };
}

function renderGraph(v, animate) {
  const legend = ["collector", "layer", "cashout", "victim", "victim_ato", "sink"].map((r) => `<span><i style="background:${ROLE[r].color}"></i>${ROLE[r].en}</span>`).join("") + "<span>- - shared device</span>";
  const ring = v && v.ring;
  if (!ring || !ring.nodes || !ring.nodes.length) {
    graphKey = "";
    clearTimeout(growTimer);
    if (network) { network.destroy(); network = null; }
    $("#graph").innerHTML = `<div class="ph" style="border:0;height:100%;display:grid;place-items:center;background:transparent">${v && v.status === "RUNNING" ? '<span><span class="spinner"></span> Waiting for the Ring Hunter to expand the ledger graph…</span>' : "No ring graph for this case yet."}</div>`;
    $("#legend").innerHTML = legend;
    if (!v || !v.ring) $("#xai").innerHTML = `<div class="ph">${v && v.status === "CLEARED" ? "False positive — no ring to graph." : "Click an account on the graph for its Shapley risk attribution."}</div>`;
    return;
  }
  const key = (v.case_id || "") + ":" + ring.nodes.length + ":" + ring.edges.length;
  if (key === graphKey && network) return;
  graphKey = key;
  $("#legend").innerHTML = legend;
  clearTimeout(growTimer);
  if (network) network.destroy();
  $("#graph").innerHTML = "";
  nodesDS = new vis.DataSet([]); edgesDS = new vis.DataSet([]);
  network = new vis.Network($("#graph"), { nodes: nodesDS, edges: edgesDS }, {
    physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -48, springLength: 85 }, stabilization: { iterations: 120 } },
    interaction: { hover: true, tooltipDelay: 120 }, edges: { selectionWidth: 0.6, hoverWidth: 0.4 },
  });
  network.on("click", (p) => { if (p.nodes.length) showXai(p.nodes[0]); });
  const byHop = {};
  ring.nodes.forEach((n) => { (byHop[n.hop ?? 9] = byHop[n.hop ?? 9] || []).push(n); });
  const hops = Object.keys(byHop).map(Number).sort((a, b) => a - b);
  const added = new Set();
  const edges = ring.edges.map(edgeObj);
  const addHop = (i) => {
    byHop[hops[i]].forEach((n) => { nodesDS.add(nodeObj(n)); added.add(n.id); });
    edgesDS.add(edges.filter((e) => !edgesDS.get(e.id) && added.has(e.from) && added.has(e.to)));
    if (i + 1 < hops.length) growTimer = setTimeout(() => addHop(i + 1), animate ? 420 : 0);
    else finish();
  };
  const finish = () => {
    setTimeout(() => { if (!network) return; network.fit({ animation: animate }); network.setOptions({ physics: { enabled: false } }); }, animate ? 900 : 300);
    const top = ring.nodes.filter((n) => n.role === "collector").sort((a, b) => b.score - a.score)[0] || ring.nodes.find((n) => n.seed);
    if (top && !$("#xai [data-acct]")) { showXai(top.id); network.selectNodes([top.id]); }
  };
  if (animate) addHop(0);
  else { nodesDS.add(ring.nodes.map(nodeObj)); edgesDS.add(edges); finish(); }
}

async function showXai(id) {
  const v = current ? view(current) : null;
  const n = (v && v.ring ? v.ring.nodes.find((x) => x.id === id) : null) || { role: "related" };
  const box = $("#xai");
  box.innerHTML = `<div class="xai"><span class="spinner"></span> <span class="text-[12px] text-muted">Computing Shapley attribution for ${esc(id)}…</span></div>`;
  let d;
  try { d = await api("/api/account/" + id); } catch (e) { box.innerHTML = `<div class="ph">${esc(e.message)}</div>`; return; }
  const r = d.risk, p = d.profile, R = ROLE[n.role] || ROLE.related;
  const color = r.score >= 0.8 ? "#BE123C" : r.score >= 0.5 ? "#D97706" : r.score >= 0.2 ? "#A16207" : "#047857";
  const maxImp = Math.max(0.01, ...r.contributions.map((x) => Math.abs(x.impact)));
  box.innerHTML = `<div class="xai fade-in" data-acct="${esc(id)}">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0"><div class="font-mono text-[14px] font-semibold">${esc(id)}</div>
        <div class="mt-1 flex flex-wrap gap-1"><span class="badge ${R.badge}">${R.en}</span><span class="badge b-slate">${esc(p.bank)}</span><span class="badge b-slate">${esc(p.kyc_channel)} · ${p.account_age_days}d</span></div>
        <div class="mt-1 text-[11.5px] text-muted">${esc(p.holder_name)} · ${p.age}y · income ${vnd(p.declared_income)}/mo</div></div>
      <div class="text-right"><div class="text-[10px] font-semibold uppercase tracking-wider text-muted">Risk (monotonic GBM)</div>
        <div class="font-mono text-3xl font-semibold" style="color:${color}">${pct(r.score)}</div><div class="text-[11px] text-muted">${esc(r.band)}</div></div>
    </div>
    <div class="mt-3 text-[10.5px] font-semibold uppercase tracking-wider text-muted">Shapley attribution vs. typical customer</div>
    <div class="mt-2 space-y-2">${r.contributions.length ? r.contributions.slice(0, 6).map((x) => `
      <div><div class="flex justify-between gap-2 text-[12px]"><span>${esc(FEATURE_EN[x.feature] || x.feature)} <span class="font-mono text-[10.5px] text-muted">${fmtVal(x.feature, x.value)} vs ${fmtVal(x.feature, x.normal_median)}</span></span>
        <span class="font-mono font-semibold" style="color:${x.impact >= 0 ? "#BE123C" : "#047857"}">${x.impact >= 0 ? "+" : ""}${(x.impact * 100).toFixed(1)}%</span></div>
        <div class="bar-track mt-1"><div class="bar-fill" style="width:${Math.abs(x.impact) / maxImp * 100}%;background:${x.impact >= 0 ? "linear-gradient(90deg,#D97706,#BE123C)" : "#047857"}"></div></div></div>`).join("")
      : `<div class="ph">Low-risk account — no material risk drivers.</div>`}</div>
    ${r.red_flags.length ? `<div class="mt-3 text-[10.5px] font-semibold uppercase tracking-wider text-amber-700">Indicators · Điều 27–28 Luật PCRT 2022</div>
      <ul class="m-0 mt-1 list-none space-y-1 p-0 text-[12px]">${r.red_flags.slice(0, 4).map((f) => `<li>• ${esc(f.text)} <span class="text-muted">— ${esc(f.legal)}</span></li>`).join("")}</ul>` : ""}
    ${r.mitigating.length ? `<div class="mt-3 text-[10.5px] font-semibold uppercase tracking-wider text-emerald-700">Mitigating factors</div>
      <ul class="m-0 mt-1 list-none space-y-1 p-0 text-[12px]">${r.mitigating.slice(0, 3).map((f) => `<li>• ${esc(f.text)}</li>`).join("")}</ul>` : ""}
  </div>`;
}

function fmtVal(f, v) {
  if (["fast_out_ratio", "foreign_ip_ratio", "night_ratio", "cashout_ratio", "pass_through", "same_holder_out_ratio", "small_in_ratio", "qr_in_ratio"].includes(f)) return pct(v);
  if (f === "income_ratio") return v.toFixed(0) + "×";
  if (f === "median_dwell_min") return v >= 10000 ? "n/a" : v.toFixed(0) + "m";
  if (f === "ekyc" || f === "is_business") return v ? "yes" : "no";
  if (f === "log_sum_in") return vndShort(Math.expm1(v));
  return Number.isInteger(v) ? String(v) : Number(v).toFixed(1);
}

// ---------- evidence ----------
function renderEvidence(v) {
  const ev = (v && v.evidence) || [];
  $("#cnt-evidence").textContent = ev.length;
  $("#pane-evidence").innerHTML = ev.length ? ev.map((e) =>
    `<div class="ev-card" id="vault-${esc(e.id)}"><div class="flex items-center gap-2"><span class="ev-tag">${esc(e.id)}</span><span class="lg">${esc(e.legal || "ledger fact")}</span></div>
      <div class="tx">${esc(e.text)}</div>${e.tx_ids && e.tx_ids.length ? `<div class="mt-1 font-mono text-[10.5px] text-muted">tx: ${e.tx_ids.slice(0, 4).map(esc).join(" · ")}</div>` : ""}</div>`).join("")
    : `<div class="ph">${v && v.status === "RUNNING" ? '<span class="spinner"></span> Evidence vault is being built…' : "No evidence for this case."}</div>`;
}

export function flashEvidence(id) {
  showPane("pane-evidence");
  const el = document.getElementById("vault-" + id);
  if (!el) return toast(`${id} is not in the evidence vault`, "error");
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
}

export function evInline(text, evidence) {
  const evm = Object.fromEntries((evidence || []).map((e) => [e.id, e.text]));
  return esc(text).replace(/\[?(EV-\d+)\]?/g, (m, id) => `<span class="ev-tag ${evm[id] ? "" : "invalid"}" data-ev="${id}" title="${esc(evm[id] || "not in vault")}">${id}</span>`);
}

// ---------- STR dossier ----------
function renderStr(v) {
  const box = $("#pane-str");
  if (!v) { box.innerHTML = `<div class="ph">No case selected.</div>`; return; }
  if (v.status === "CLEARED" && v.clearance) {
    const cl = v.clearance;
    box.innerHTML = `<div class="judge-ok"><i data-lucide="badge-check" class="h-5 w-5 shrink-0"></i><div><b>No STR required — alert closed as false positive</b><div class="text-[12px]">${esc(cl.note)}</div></div></div>
      <div class="dossier"><h2>BIÊN BẢN RÀ SOÁT CẢNH BÁO (DƯƠNG TÍNH GIẢ)</h2><div class="sub">Mã vụ việc ${esc(v.case_id)}</div>
      <h4>Kết luận</h4><p>${esc(cl.verdict)}.</p><h4>Tài khoản được rà soát</h4>${cl.accounts.map((a) => `<p><span class="mono">${esc(a.account_id)}</span> – ${esc(a.holder)} (${esc(a.segment)}), điểm rủi ro ${pct(a.score)}.</p>
      <ul>${a.mitigating.map((m) => `<li>${esc(m.text)} <i>(${esc(m.legal)})</i></li>`).join("")}</ul>`).join("")}</div>`;
    return;
  }
  if (!v.str) {
    box.innerHTML = v.draft ? `<div class="ph" style="text-align:left"><span class="spinner"></span> <b>Judge Agent is fact-checking the draft…</b><div class="mt-2 text-[12.5px] text-ink">${evInline(v.draft.tom_tat || "", v.evidence)}</div></div>`
      : v.status === "RUNNING" ? `<div class="space-y-2 rounded-xl border border-line bg-white p-4"><div class="skeleton" style="width:60%"></div><div class="skeleton"></div><div class="skeleton" style="width:85%"></div><div class="skeleton" style="width:70%"></div><div class="pt-1 text-[12px] text-muted">The Investigator Agent drafts once the evidence vault is complete.</div></div>`
      : `<div class="ph">No STR for this case.</div>`;
    bindEv(box, v);
    return;
  }
  const j = v.judge || {}, s = v.str;
  const verified = (j.checked || []).filter((x) => x.ok).length, rep = (j.repaired || []).length;
  const sc = j.rubric && j.rubric.scores ? Object.values(j.rubric.scores).filter((x) => typeof x === "number") : [];
  const avg = sc.length ? (sc.reduce((a, b) => a + b, 0) / sc.length).toFixed(1) : null;
  const tag = (ids) => (ids || []).map((id) => evInline(id, v.evidence)).join("");
  box.innerHTML = `<div class="judge-ok"><i data-lucide="shield-check" class="h-5 w-5 shrink-0"></i><div><b>Judge certified: every final claim traces to the evidence vault</b>
      <div class="text-[12px]">${verified}/${(j.checked || []).length} draft claims passed the number-by-number check${rep ? ` · ${rep} auto-repaired from ledger data` : ""}${avg ? ` · rubric ${avg}/5` : ""} · drafted by ${esc(s.mode === "llm" ? "GreenNode MaaS" : "template (offline)")}</div></div></div>
    <div class="mb-2 flex justify-end"><button class="btn btn-outline btn-sm" id="btn-export"><i data-lucide="file-down"></i>Export for officer review</button></div>
    <div class="dossier" id="dossier"><h2>${esc(s.title)}</h2><div class="sub">Mã vụ việc ${esc(s.case_id)} · lập ${esc(s.created)}</div>
    <h4>1. Đối tượng báo cáo</h4><p>${esc(s.reporting_entity)}<br>Căn cứ: ${esc(s.basis)}<br>Hạn nộp: <b>${esc(s.deadline)}</b></p>
    <h4>2. Tóm tắt</h4><p>${evInline(s.tom_tat, v.evidence)}</p>
    <h4>3. Tài khoản liên quan</h4><table><tr><th>Số tài khoản</th><th>Chủ TK (che)</th><th>Vai trò</th><th>Rủi ro</th></tr>
      ${s.accounts.map((a) => `<tr><td class="mono">${esc(a.account_id)}</td><td>${esc(a.holder)}</td><td>${esc({ collector: "Gom tiền", layer: "Trung chuyển", cashout: "Rút/chuyển ra" }[a.role] || a.role)}</td><td>${pct(a.score)}</td></tr>`).join("")}</table>
    <p>Tổng tiền nạn nhân chuyển vào: <b>${esc(s.total_victim_loss)}</b> ${tag(["EV-02"])} · Ước còn trong đường dây: <b>${esc(s.est_remaining)}</b> ${tag(["EV-02"])}</p>
    <h4>4. Nhận định thủ đoạn</h4><p>${evInline(s.nhan_dinh_thu_doan, v.evidence)}</p>
    <h4>5. Dấu hiệu đáng ngờ &amp; bằng chứng</h4><ol>${(s.dau_hieu || []).map((d) => `<li>${esc(d.noi_dung)} ${tag(d.ev)} ${d.can_cu ? `<span style="color:#7B5E68">[${esc(d.can_cu)}]</span>` : ""}</li>`).join("")}</ol>
    <h4>6. Đề xuất</h4><ul>${(s.de_xuat || []).map((x) => `<li>${evInline(x, v.evidence)}</li>`).join("")}</ul></div>`;
  bindEv(box, v);
  $("#btn-export").onclick = () => exportDossier(v);
}

function bindEv(root, v) { $$("[data-ev]", root).forEach((t) => t.onclick = () => flashEvidence(t.dataset.ev)); }

function exportDossier(v) {
  const html = `<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>${esc(v.case_id)} – STR draft</title>
    <style>body{font-family:system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#2A0E19;line-height:1.6}h2{text-align:center;color:#5A0F2E}
    table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #EADBDD;padding:4px 6px;text-align:left;font-size:13px}
    .ev-tag{font-family:monospace;font-size:11px;background:#FFF8E8;color:#A16207;border:1px solid #E6CC94;border-radius:4px;padding:0 4px}</style></head>
    <body>${$("#dossier").innerHTML}<h4>Phụ lục – Kho bằng chứng</h4><ul>${v.evidence.map((e) => `<li><b>${esc(e.id)}</b>: ${esc(e.text)}</li>`).join("")}</ul>
    <p style="color:#7B5E68;font-size:12px">Dự thảo do COUNTER-SNARE tạo – cần chuyên viên PCRT rà soát và ký trước khi nộp.</p></body></html>`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  a.download = `${v.case_id}_STR_draft.html`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast("STR dossier exported for officer review.");
}

// ---------- legal actions (Human-in-the-Loop) ----------
const ACT_ICON = { delay_transactions: "timer-off", submit_str: "landmark", notify_victims: "phone-call", freeze_account: "snowflake", dismiss_alert: "circle-off" };

export function actionsHtml(run) {
  const v = view(run);
  const acts = v.actions || [];
  const ready = !!(run.result && run.result.status !== "ERROR");
  return acts.map((a) => {
    const t = TOOL_EN[a.tool] || { label: a.title };
    const decided = /DUYỆT bởi|TỪ CHỐI bởi/.test(a.status);
    const cls = /DUYỆT bởi/.test(a.status) ? "b-emerald" : /TỪ CHỐI/.test(a.status) ? "b-slate" : /CHỜ|CẦN/.test(a.status) ? "b-amber" : "b-cyan";
    return `<div class="act"><span class="av" style="--c:${a.tool === "freeze_account" ? "#BE123C" : "#7A1238"}"><i data-lucide="${ACT_ICON[a.tool] || "gavel"}"></i></span>
      <div class="info"><div class="ttl">${esc(t.label)} <span class="badge ${cls}">${esc(englishStatus(a.status))}</span></div>
        <div class="legal">${esc(a.title)}${a.accounts ? ` · ${a.accounts.length} accounts` : ""}${a.deadline ? ` · deadline ${esc(a.deadline)}` : ""}</div>
        <div class="legal">${esc(a.legal)}</div>
        ${a.agent_attempt && a.agent_attempt !== "ALLOW" ? `<div class="legal" style="color:#BE123C">Agent tried this itself → DENY by Policy Gateway (rule #4). Needs an officer.</div>` : ""}</div>
      <div class="btns">${decided ? "" : `<button class="btn btn-primary btn-sm" data-approve="${esc(a.id)}" ${ready ? "" : "disabled"}><i data-lucide="check"></i>${a.tool === "dismiss_alert" ? "Confirm" : "Approve"}</button>
        <button class="btn btn-outline btn-sm" data-reject="${esc(a.id)}" ${ready ? "" : "disabled"}>Reject</button>`}</div></div>`;
  }).join("");
}

function renderActions(run) {
  const v = run ? view(run) : null;
  const acts = (v && v.actions) || [];
  $("#cnt-actions").textContent = acts.filter((a) => !/DUYỆT bởi|TỪ CHỐI bởi/.test(a.status)).length;
  $("#pane-actions").innerHTML = acts.length ? `<div class="hitl" style="margin-left:0"><div class="cap"><i data-lucide="user-check" class="h-4 w-4"></i>Human-in-the-loop approval gate<small>Policy: agent may read &amp; draft only</small></div>${actionsHtml(run)}</div>`
    : `<div class="ph">${v && v.status === "RUNNING" ? "Agents are still working — proposed legal actions will appear here." : "No legal action proposed."}</div>`;
}

export function bindActionButtons(root, run, onDone) {
  $$("[data-approve]", root).forEach((b) => b.onclick = () => decide(run, b.dataset.approve, "approve", onDone));
  $$("[data-reject]", root).forEach((b) => b.onclick = () => decide(run, b.dataset.reject, "reject", onDone));
}

export function officerName() { try { return localStorage.getItem("cs.officer") || ""; } catch (e) { return ""; } }
export function setOfficerName(n) { try { localStorage.setItem("cs.officer", n); } catch (e) { /* ignore */ } }

export function openModal({ title, body, confirm, onSubmit }) {
  const m = $("#modal");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = body + `<div id="modal-err" class="err" hidden></div>`;
  $("#modal-foot").innerHTML = `<button type="button" class="btn btn-outline" id="modal-cancel">Cancel</button><button type="submit" class="btn btn-primary">${confirm}</button>`;
  m.classList.add("open");
  icons();
  const close = () => { m.classList.remove("open"); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  $("#modal-close").onclick = close; $("#modal-cancel").onclick = close;
  m.onclick = (e) => { if (e.target === m) close(); };
  $("#modal-form").onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#modal-err"); err.hidden = true;
    try { await onSubmit(); close(); } catch (ex) { err.textContent = ex.message; err.hidden = false; }
  };
  setTimeout(() => { const f = $("#modal-body input"); f && f.focus(); }, 40);
}

function decide(run, actionId, decision, onDone) {
  const act = (view(run).actions || []).find((a) => a.id === actionId);
  if (!act) return;
  const t = TOOL_EN[act.tool] || { label: act.title, legal: act.legal };
  const approve = decision === "approve";
  openModal({
    title: approve ? "Officer sign-off" : "Reject proposed action",
    confirm: approve ? (act.tool === "dismiss_alert" ? "Confirm closure" : "Approve & sign") : "Reject",
    body: `<div><b>${esc(t.label)}</b> · case <span class="mono">${esc(run.case_id)}</span><div class="mt-1 text-[12px] text-muted">${esc(act.legal || t.legal || "")}</div></div>
      <label class="text-[12px] font-semibold">AML officer name<input id="m-officer" class="input mt-1" value="${esc(officerName())}" autocomplete="off" required></label>
      ${approve && act.tool === "freeze_account" ? `<label class="text-[12px] font-semibold">Competent-authority decision No. (Art. 45)<input id="m-decision" class="input mt-1" placeholder="e.g. 125/QĐ-CSĐT" autocomplete="off" required></label>` : ""}
      ${approve ? `<label class="flex items-start gap-2 text-[12px]"><input id="m-attest" type="checkbox" style="accent-color:#7A1238;margin-top:2px">I reviewed the evidence vault and the STR draft for this case.</label>`
        : `<label class="text-[12px] font-semibold">Reason (optional)<input id="m-note" class="input mt-1" autocomplete="off"></label>`}`,
    onSubmit: async () => {
      const officer = $("#m-officer").value.trim();
      if (!officer) throw new Error("Officer name is required.");
      if (approve && !$("#m-attest").checked) throw new Error("Please attest that you reviewed the evidence.");
      const r = await api("/api/approve", { case_id: run.case_id, action_id: actionId, officer, decision,
        authority_decision: $("#m-decision") ? $("#m-decision").value : "", note: $("#m-note") ? $("#m-note").value : "" });
      setOfficerName(officer);
      act.status = r.action.status;
      toast(`${t.label}: ${approve ? "approved" : "rejected"} by ${officer} · written to the audit trail.`);
      onDone && onDone();
    },
  });
}
