// Operations Center: live threat inbox → autonomous Orchestrator run → Agentic Thought Stream (polling the event bus)
import { $, $$, api, esc, icons, toast, vndShort, avatar, AGENTS, MODEL_SHORT } from "./core.js";
import { actionsHtml, bindActionButtons, evInline, flashEvidence, officerName, openModal, renderBoard, setOfficerName, showPane, view } from "./board.js";

const S = { inbox: [], runs: {}, active: null, autopilot: false, bootAt: Date.now() };
const CH_ICON = { app: "smartphone", zalo: "message-circle", hotline: "phone", email: "mail", branch: "landmark", tm: "radar", sms: "message-square", telegram: "send" };
const PRIO = { critical: 0, high: 1, medium: 2, low: 3 };
const ROSTER = ["Orchestrator", "Guardrail Agent", "Intel Agent", "Ring Hunter", "Risk Engine", "Decoy Agent", "Investigator Agent", "Judge Agent", "Policy Gateway", "Memory Agent", "Analyst Copilot"];
const SUGGEST = ["Why is the seed account a mule?", "Tiền còn lại trong đường dây là bao nhiêu?", "What happens if I approve the delay?", "Bằng chứng nào cho thấy dùng chung thiết bị?"];

export async function initOps() {
  renderRoster(null);
  renderCaseHead(null);
  renderEmpty();
  renderBoard(null);
  $$(".seg button").forEach((b) => b.onclick = () => showPane(b.dataset.pane));
  try { S.autopilot = localStorage.getItem("cs.autopilot") === "1"; } catch (e) { /* ignore */ }
  $("#autopilot").checked = S.autopilot;
  $("#autopilot").onchange = (e) => {
    S.autopilot = e.target.checked;
    try { localStorage.setItem("cs.autopilot", S.autopilot ? "1" : "0"); } catch (x) { /* ignore */ }
    toast(S.autopilot ? "Autopilot engaged — the Orchestrator will pick up new threats by priority." : "Autopilot off — dispatch threats manually.");
    autopilotTick();
  };
  $("#composer").onsubmit = (e) => {
    e.preventDefault();
    const text = $("#composer-text").value.trim();
    if (!text) return toast("Paste a message or alert first.", "error");
    const sel = $("#composer-channel");
    const item = addItem({ id: "MAN-" + Date.now().toString(36).toUpperCase(), channel: sel.value, channel_label: sel.options[sel.selectedIndex].text,
      sender: officerName() || "Analyst", text, priority: "high", origin: "analyst" }, true);
    $("#composer-text").value = "";
    dispatch(item);
  };
  $("#btn-sim").onclick = () => simulate("report", $("#btn-sim"));
  $("#btn-sim-fc").onclick = () => simulate("first_contact", $("#btn-sim-fc"));
  $("#copilot").onsubmit = (e) => { e.preventDefault(); ask($("#copilot-q").value); };
  $("#suggest").innerHTML = SUGGEST.map((q) => `<button type="button">${esc(q)}</button>`).join("");
  $$("#suggest button").forEach((b) => b.onclick = () => ask(b.textContent));
  const [ib, rs] = await Promise.all([api("/api/ops/inbox"), api("/api/ops/runs").catch(() => ({ runs: [] }))]);
  // shared workspace: cases already opened on this runtime (by any analyst) are restored, newest first
  const recent = rs.runs.slice(0, 12).reverse();
  const linked = new Map(recent.filter((r) => r.meta.inbox_id).map((r) => [r.meta.inbox_id, r]));
  ib.items.forEach((it) => {
    const r = linked.get(it.id);
    if (r || !it.arrive_after_s) { const item = addItem(it, false); if (r) restore(item, r); }
    else setTimeout(() => { addItem(it, true); toast(`New threat · ${it.channel_label}`); }, it.arrive_after_s * 1000);
  });
  recent.filter((r) => !r.meta.inbox_id || !ib.items.some((i) => i.id === r.meta.inbox_id)).forEach((r) => {
    restore(addItem({ id: r.meta.inbox_id || r.case_id, channel: r.meta.channel || "app", channel_label: r.meta.channel_label || "Analyst manual entry",
      sender: r.meta.sender || "Analyst", text: r.meta.text || "", priority: "high" }, false), r);
  });
  setInterval(() => { renderInbox(); renderTicker(); if (S.active) renderCaseHead(S.runs[S.active]); }, 1000);
  setInterval(autopilotTick, 2500);
  renderTicker();
}

// ---------------- inbox ----------------
function addItem(it, fresh) {
  const item = { ...it, arrivedAt: Date.now(), status: "new", fresh };
  S.inbox.unshift(item);
  renderInbox();
  return item;
}

function ago(t) { const s = Math.round((Date.now() - t) / 1000); return s < 5 ? "just now" : s < 60 ? s + "s ago" : Math.floor(s / 60) + "m ago"; }

function itemStatus(it) {
  const run = it.case_id && S.runs[it.case_id];
  if (!run) return it.status === "dispatching" ? ["Dispatching…", "b-gold", true] : ["New", "b-gold"];
  if (!run.done) return [run.phase || "Agents working", "b-gold", true];
  const r = run.result || {};
  if (r.status === "CLEARED") return ["Closed · false positive", "b-emerald"];
  if (r.status === "PENDING_APPROVAL") {
    const open = (r.actions || []).filter((a) => /CHỜ|CẦN/.test(a.status)).length;
    return [open ? `Awaiting approval (${open})` : "Actioned", open ? "b-rose" : "b-emerald"];
  }
  if (r.status === "ERROR") return ["Error", "b-rose"];
  return [r.playbook === "interbank_referral" ? "Interbank referral" : "No seed on ledger", "b-slate"];
}

function renderInbox() {
  // keyed, in-place DOM updates: never replace an item under the user's cursor (a rebuilt node would swallow the click)
  const box = $("#inbox");
  $("#inbox-count").textContent = S.inbox.length;
  if (!S.inbox.length) { box.innerHTML = `<div class="ph">Inbox empty.</div>`; return; }
  const ph = box.querySelector(".ph"); if (ph) ph.remove();
  S.inbox.forEach((it, idx) => {
    let el = it.el;
    if (!el) {
      el = document.createElement("button");
      el.type = "button";
      el.className = "th-item" + (it.fresh ? " th-new" : "");
      el.innerHTML = `<div class="top"><span class="ch"><i data-lucide="${CH_ICON[it.channel] || "inbox"}"></i></span><span class="src">${esc(it.channel_label)}</span><span class="when"></span></div>
        <div class="txt">${esc(it.text)}</div>
        <div class="foot"><span class="badge prio-${esc(it.priority || "medium")}">${esc((it.priority || "medium").toUpperCase())}</span><span class="badge st"></span>
          ${it.mode === "llm" ? '<span class="badge b-cyan" title="Written just now by the threat simulator (GreenNode MaaS)">LLM-generated</span>' : ""}
          <span class="ml-auto text-[10.5px] text-muted">${esc(it.sender || "")}</span></div>`;
      el.onclick = () => { if (it.case_id) setActive(it.case_id); else dispatch(it); };
      it.el = el;
      it.fresh = false;
      icons();
    }
    if (box.children[idx] !== el) box.insertBefore(el, box.children[idx] || null);
    el.classList.toggle("active", !!it.case_id && it.case_id === S.active);
    el.querySelector(".when").textContent = ago(it.arrivedAt);
    const [st, cls, spin] = itemStatus(it);
    const key = st + cls + spin;
    if (el.dataset.st !== key) {
      el.dataset.st = key;
      const b = el.querySelector(".st");
      b.className = "badge st " + cls;
      b.innerHTML = (spin ? '<span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span>' : "") + esc(st);
    }
  });
  if (!S.inbox.length) box.innerHTML = `<div class="ph">Inbox empty.</div>`;
}

async function simulate(kind, btn) {
  btn.disabled = true;
  const label = btn.innerHTML;
  btn.innerHTML = `<span class="spinner"></span>Generating…`;
  try {
    const t = await api("/api/ops/simulate", { kind });
    addItem(t, true);
    toast(t.mode === "llm" ? "New unseen threat written by GreenNode MaaS — dispatch it or let Autopilot pick it up." : "New synthetic threat added (template mode).");
  } catch (e) { toast(e.message, "error"); }
  finally { btn.disabled = false; btn.innerHTML = label; icons(); }
}

function autopilotTick() {
  if (!S.autopilot) return;
  const running = Object.values(S.runs).filter((r) => !r.done).length;
  if (running) return;
  const next = S.inbox.filter((i) => i.status === "new" && !i.case_id).sort((a, b) => (PRIO[a.priority] ?? 9) - (PRIO[b.priority] ?? 9) || a.arrivedAt - b.arrivedAt)[0];
  if (next) dispatch(next, true);
}

function restore(item, r) {
  item.case_id = r.case_id;
  item.status = "running";
  S.runs[r.case_id] = { case_id: r.case_id, item, events: [], next: 0, done: false, result: null, partial: {}, t0: null, lastTs: null, queue: [], phase: "Agents working", auto: r.meta.origin === "autopilot", restored: true };
  poll(r.case_id);
}

// ---------------- dispatch + polling ----------------
async function dispatch(item, auto = false) {
  if (item.status !== "new") return;
  item.status = "dispatching";
  renderInbox();
  try {
    const { case_id } = await api("/api/ops/run", { text: item.text, inbox_id: item.id, channel: item.channel, channel_label: item.channel_label,
      sender: item.sender, campaign_id: item.campaign_id, origin: auto ? "autopilot" : item.origin || "analyst" });
    item.case_id = case_id;
    item.status = "running";
    S.runs[case_id] = { case_id, item, events: [], next: 0, done: false, result: null, partial: {}, t0: null, lastTs: null, queue: [], phase: "Agents working", auto };
    const viewing = S.active && S.runs[S.active];
    if (!auto || !viewing || viewing.done) setActive(case_id);
    poll(case_id);
  } catch (e) { item.status = "new"; toast(e.message, "error"); renderInbox(); }
}

async function poll(cid, once = false) {
  const run = S.runs[cid];
  try {
    const r = await api(`/api/ops/events/${cid}?after=${run.next}`);
    run.next = r.next;
    r.events.forEach((ev) => ingest(run, ev));
    if (r.done && !run.done) { run.done = true; run.result = r.result; onDone(run); }
  } catch (e) { /* transient: retry */ }
  if (!once && !run.done) setTimeout(() => poll(cid), 650);
}

function ingest(run, ev) {
  run.events.push(ev);
  if (run.t0 === null) run.t0 = ev.ts;
  run.lastTs = ev.ts;
  if (ev.type === "partial") { run.partial[ev.key] = ev.data; }
  if (ev.type === "node" && ev.status === "start") run.phase = (ev.agent || "Agents") + " working";
  if (S.active === run.case_id) {
    run.queue.push(ev);
    drain(run);
  }
}

// render queued events with a small stagger so a burst reads as a stream (data is real, only the paint is paced)
function drain(run) {
  if (run.draining) return;
  run.draining = true;
  const step = () => {
    if (S.active !== run.case_id) { run.draining = false; return; }
    const ev = run.queue.shift();
    if (!ev) { run.draining = false; return; }
    renderEvent(run, ev, true);
    setTimeout(step, run.queue.length > 30 ? 10 : 55);
  };
  step();
}

function onDone(run) {
  if (run.result && run.result.status !== "ERROR") run.partial = {};
  if (S.active === run.case_id) {
    renderBoard(run, { animate: false });
    renderCaseHead(run);
    enableCopilot(run);
    refreshHitl(run);
  }
  const r = run.result || {};
  if (r.status === "PENDING_APPROVAL" && !run.restored) toast(`${run.case_id}: ring mapped — ${(r.actions || []).length} actions await your approval.`);
  renderInbox();
  renderTicker();
}

// ---------------- active case ----------------
function setActive(cid) {
  S.active = cid;
  const run = S.runs[cid];
  run.queue = [];
  run.draining = false;
  $("#stream").innerHTML = "";
  run.ui = { tools: [], llm: [], node: {} };
  run.events.forEach((ev) => renderEvent(run, ev, false));
  renderBoard(run, { animate: !run.done });
  renderCaseHead(run);
  renderRoster(run);
  enableCopilot(run);
  renderInbox();
  scrollStream(true);
}

function enableCopilot(run) {
  const ok = run && run.done && run.result && run.result.status !== "ERROR";
  $("#copilot-q").disabled = !ok; $("#copilot-send").disabled = !ok;
  $("#copilot-q").placeholder = ok ? "Ask the Copilot about this case — answers cite the evidence vault only" : "The Copilot unlocks when the agents finish this case…";
}

function renderCaseHead(run) {
  const box = $("#case-head");
  if (!run) { box.innerHTML = `<span class="text-[12.5px] text-muted"><b class="text-ink">Agents on standby.</b> Select a threat, report a new one, or engage Autopilot.</span>`; return; }
  const r = run.result || {};
  const [label, cls] = !run.done ? ["Investigating", "running"] : r.status === "PENDING_APPROVAL" ? ["Awaiting approval", "pending"] : r.status === "CLEARED" ? ["False positive closed", "cleared"] : [r.status || "Done", "other"];
  const secs = r.total_ms ? r.total_ms / 1000 : run.t0 ? (run.done ? run.lastTs - run.t0 : Date.now() / 1000 - run.t0) : 0;
  const count = (f) => run.events.filter(f).length;
  box.innerHTML = `<span class="status ${cls}">${!run.done ? '<span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span>' : ""}${esc(label)}</span>
    <span class="cid">${esc(run.case_id)}</span>
    <span class="meta"><span>${esc(run.item.channel_label)}</span><span>⏱ <b>${Math.max(0, secs).toFixed(1)}s</b></span>
      <span>LLM calls <b>${count((e) => e.type === "audit" && e.kind === "llm_call")}</b></span><span>tool calls <b>${count((e) => e.type === "tool" && e.status === "done")}</b></span>
      <span>policy checks <b>${count((e) => e.type === "audit" && e.kind === "policy")}</b></span>${run.auto ? '<span class="badge b-wine">AUTOPILOT</span>' : ""}</span>`;
}

function renderRoster(run) {
  const st = {};
  if (run) run.events.forEach((e) => {
    if (e.type === "node") st[e.agent] = e.status === "start" ? "working" : "done";
    if (e.type === "tool" && e.agent === "Risk Engine") st[e.agent] = e.status === "start" ? "working" : "done";
    if (e.type === "tool" && e.agent === "Memory Agent" && e.status === "done") st[e.agent] = "done";
    if (e.type === "thought" && e.level === "alert" && e.agent !== "Orchestrator") st[e.agent] = "alert";
    if (e.type === "copilot") st["Analyst Copilot"] = e.who === "analyst" ? "working" : "done";
  });
  if (run && run.done) ROSTER.forEach((a) => { if (st[a] === "working") st[a] = "done"; });
  $("#roster").innerHTML = ROSTER.map((a) => `<span class="agent-chip ${st[a] || ""}" title="${esc(a)}">${avatar(a)}${esc(a.replace(" Agent", ""))}<span class="light"></span></span>`).join("");
  icons();
}

function renderEmpty() {
  $("#stream").innerHTML = `<div class="empty"><span class="av" style="--c:#7A1238;width:52px;height:52px;margin:0 auto"><i data-lucide="workflow"></i></span>
    <h3>Agentic Thought Stream</h3>
    <p>Every reasoning step, tool call, GreenNode MaaS request and policy decision is streamed here live. You hand over a threat — the
      <b>Orchestrator</b> decides which agents to dispatch. Legal actions stop at your approval.</p>
    <div class="flow"><div><b>Screen</b>Guardrails quarantine prompt-injection and mask PII.</div><div><b>Hunt</b>Ring Hunter expands the ledger graph from the seed.</div>
      <div><b>Draft &amp; verify</b>STR drafted by the LLM, every number fact-checked.</div><div><b>Decide</b>Policy Gateway blocks the agent; you sign off.</div></div>
    <div class="flex flex-wrap justify-center gap-2"><button type="button" class="btn btn-primary" id="empty-top"><i data-lucide="play"></i>Investigate top-priority threat</button>
      <button type="button" class="btn btn-outline" id="empty-auto"><i data-lucide="bot"></i>Engage Autopilot</button></div></div>`;
  icons();
  $("#empty-top").onclick = () => {
    const next = S.inbox.filter((i) => i.status === "new").sort((a, b) => (PRIO[a.priority] ?? 9) - (PRIO[b.priority] ?? 9))[0];
    next ? dispatch(next) : toast("No new threat in the inbox.", "error");
  };
  $("#empty-auto").onclick = () => { $("#autopilot").checked = true; $("#autopilot").dispatchEvent(new Event("change")); };
}

// ---------------- event rendering ----------------
const rel = (run, ev) => "+" + Math.max(0, ev.ts - run.t0).toFixed(1) + "s";
const argStr = (a) => Object.entries(a || {}).map(([k, v]) => `${k}=${Array.isArray(v) ? "[" + v.slice(0, 3).join(", ") + (v.length > 3 ? ", …" : "") + "]" : v}`).join("  ");
const resStr = (r) => Object.entries(r || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? (v.length ? (Array.isArray(v[0]) ? v.map((x) => x.join(" ")).join(", ") : v.slice(0, 4).join(", ")) : "none") : v ?? "—"}`).join(" · ");

function append(html) {
  const s = $("#stream");
  if (s.querySelector(".empty")) s.innerHTML = "";
  s.insertAdjacentHTML("beforeend", html);
  const el = s.lastElementChild;
  icons();
  return el;
}

function scrollStream(force) {
  const s = $("#stream");
  if (force || s.scrollHeight - s.scrollTop - s.clientHeight < 160) s.scrollTop = s.scrollHeight;
}

function renderEvent(run, ev, live) {
  const ui = run.ui || (run.ui = { tools: [], llm: [], node: {} });
  const who = (agent) => `<div class="who"><b>${esc(agent)}</b><span class="t">${rel(run, ev)}</span></div>`;
  const c = (AGENTS[ev.agent] || {}).c || "#7A1238";
  if (!["decoy", "llm", "audit"].includes(ev.type)) ui.decoyOpen = false;
  switch (ev.type) {
    case "node":
      if (ev.status === "start") { ui.node[ev.agent + ev.node] = append(`<div class="divider">${esc(ev.agent)}<span class="ms"></span></div>`); }
      else { const d = ui.node[ev.agent + ev.node]; if (d) d.querySelector(".ms").textContent = `· ${(ev.ms / 1000).toFixed(1)}s`; }
      break;
    case "thought":
      append(`<div class="ev">${avatar(ev.agent)}<div class="body">${who(ev.agent)}<div class="thought ${esc(ev.level || "")}">${esc(ev.text)}</div></div></div>`);
      break;
    case "tool": {
      const pending = ui.tools.find((t) => t.agent === ev.agent && t.tool === ev.tool && !t.done);
      if (ev.status === "start" || !pending) {
        const el = append(`<div class="tool" style="--c:${c}"><div class="head"><i data-lucide="wrench" class="h-3.5 w-3.5" style="color:${c}"></i><span class="name">${esc(ev.tool)}</span>
          <span class="args">${esc(argStr(ev.args))}</span><span class="ms">${ev.status === "start" ? '<span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span>' : (ev.ms ?? 0) + " ms"}</span></div>
          <div class="pol"></div>${ev.status === "done" ? `<div class="res">→ ${esc(resStr(ev.result))}</div>` : ""}</div>`);
        ui.tools.push({ agent: ev.agent, tool: ev.tool, el, done: ev.status === "done", pol: {} });
      } else {
        pending.done = true;
        pending.el.querySelector(".ms").textContent = (ev.ms ?? 0) + " ms";
        pending.el.insertAdjacentHTML("beforeend", `<div class="res">→ ${esc(resStr(ev.result))}</div>`);
      }
      break;
    }
    case "llm": {
      const html = `<div class="llm"><i data-lucide="cpu" class="h-3.5 w-3.5"></i><b>GreenNode MaaS</b><span>${esc(MODEL_SHORT[ev.model] || ev.model)}</span>
        <span class="mono">${esc(ev.purpose)}</span><span class="st"><span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span></span></div>`;
      let el;
      if (ui.decoyOpen && String(ev.purpose).startsWith("honeypot")) {
        ui.decoy.insertAdjacentHTML("beforeend", html);
        el = ui.decoy.lastElementChild; el.style.marginLeft = "0"; el.style.alignSelf = ev.purpose === "honeypot_batu" ? "flex-end" : "flex-start";
        icons();
      } else el = append(html);
      ui.llm.push({ purpose: ev.purpose, model: ev.model, el, done: false });
      break;
    }
    case "audit": renderAudit(run, ev, ui, live); break;
    case "partial":
      if (S.active === run.case_id && live) renderBoard(run, { animate: true });
      if (ev.key === "actions") {
        const el = append(`<div class="hitl" data-hitl><div class="cap"><i data-lucide="user-check" class="h-4 w-4"></i>Your decision is required<small>Policy Gateway escalated ${ev.data.length} actions</small></div><div class="acts">${actionsHtml(run)}</div></div>`);
        ui.hitl = el;
        bindActionButtons(el, run, () => afterDecision(run));
      }
      break;
    case "decoy": {
      let box = ui.decoyOpen && ui.decoy && ui.decoy.isConnected ? ui.decoy : null;
      if (!box) { box = append(`<div class="decoy"><div class="cap"><i data-lucide="fish" class="h-3.5 w-3.5"></i>Decoy channel · simulated conversation · persona “Bà Tư”, 68</div></div>`); ui.decoy = box; }
      ui.decoyOpen = true;
      const wcls = ev.who === "scammer" ? "scammer" : ev.who === "batu" ? "batu" : "sys";
      box.insertAdjacentHTML("beforeend", `<div class="bubble ${wcls}">${wcls === "sys" ? "" : `<span class="w">${ev.who === "scammer" ? "Scammer (simulated)" : "Decoy · Bà Tư"}</span>`}${esc(ev.text)}</div>`);
      break;
    }
    case "copilot": {
      const v = view(run);
      if (ev.who === "analyst") append(`<div class="bubble analyst"><span class="w">${esc(officerName() || "Analyst")}</span>${esc(ev.text)}</div>`);
      else {
        const el = append(`<div class="ev">${avatar("Analyst Copilot")}<div class="body">${who("Analyst Copilot")}<div class="copilot-msg">${evInline(ev.text, v.evidence)}
          ${(ev.removed_citations || []).length ? `<div class="mt-1 text-[11px] text-rose-700">Removed citations not in the vault: ${esc(ev.removed_citations.join(", "))}</div>` : ""}
          <div class="mt-1 text-[10.5px] text-muted">${ev.mode === "llm" ? "Grounded answer · GreenNode MaaS" : ev.mode === "guardrail" ? "Blocked by guardrail" : "Offline template"} · cites ${ev.citations && ev.citations.length ? ev.citations.length + " evidence items" : "no evidence"}</div></div></div></div>`);
        $$("[data-ev]", el).forEach((t) => t.onclick = () => flashEvidence(t.dataset.ev));
      }
      break;
    }
    case "done": {
      const r = run.result || {};
      append(`<div class="final"><i data-lucide="flag" class="h-4 w-4 shrink-0"></i><div><b>Mission complete</b> · playbook <span class="mono">${esc(r.playbook || "—")}</span> · ${run.events.filter((e) => e.type === "audit" && e.kind === "llm_call").length} LLM calls ·
        ${run.events.filter((e) => e.type === "tool" && e.status === "done").length} tool calls. ${r.status === "PENDING_APPROVAL" ? "Review the board and decide on the actions above." : ""}</div></div>`);
      break;
    }
    default: break;
  }
  if (live) { scrollStream(false); if (["node", "tool", "thought", "copilot"].includes(ev.type)) renderRoster(run); renderCaseHead(run); }
}

function renderAudit(run, ev, ui, live) {
  if (ev.kind === "llm_call") {
    const p = ui.llm.find((x) => !x.done && x.purpose === ev.purpose && x.model === ev.model);
    const txt = ev.ok ? `${(ev.latency_ms / 1000).toFixed(1)}s · ${ev.prompt_tokens ?? "?"}→${ev.completion_tokens ?? "?"} tok` : "failed → fallback";
    if (p) { p.done = true; p.el.querySelector(".st").textContent = txt; if (!ev.ok) p.el.classList.add("err"); }
    else append(`<div class="llm ${ev.ok ? "" : "err"}"><i data-lucide="cpu" class="h-3.5 w-3.5"></i><b>GreenNode MaaS</b><span>${esc(MODEL_SHORT[ev.model] || ev.model)}</span><span class="mono">${esc(ev.purpose)}</span><span>${txt}</span></div>`);
    return;
  }
  if (ev.kind === "policy") {
    if (ev.effect === "DENY") {
      append(`<div class="deny"><div class="flex items-center gap-2 font-semibold"><i data-lucide="octagon-x" class="h-4 w-4"></i>Policy Gateway · first match wins → DENY</div>
        <div class="mono mt-1">principal=${esc(ev.principal)}  tool=${esc(ev.tool)}  policy=pg-bay-nguoc-aml</div>
        <div class="mt-1">Enforced at the tool-gateway layer, not by a prompt. Only role:aml-officer may execute this.</div></div>`);
      return;
    }
    if (ev.principal !== "agent:bay-nguoc") return; // officer decisions are shown on their own approval card
    const t = [...ui.tools].reverse().find((x) => !x.done) || ui.tools[ui.tools.length - 1];
    if (!t) return;
    const key = ev.principal + ev.tool;
    t.pol[key] = (t.pol[key] || 0) + 1;
    t.el.querySelector(".pol").innerHTML = Object.entries(t.pol).map(([k, n]) => {
      const tool = k.replace(/^(agent:bay-nguoc|role:aml-officer)/, "");
      return `<span class="badge b-emerald"><i data-lucide="lock-keyhole" class="h-3 w-3"></i>policy ALLOW · ${esc(tool)}${n > 1 ? " ×" + n : ""}</span>`;
    }).join("");
    icons();
    return;
  }
  if (ev.kind === "guardrail" && ev.subtype === "hallucination_blocked") {
    append(`<div class="deny"><b>Guardrail · hallucination blocked</b><div class="mt-1">${esc(ev.detail || "")}</div></div>`);
    return;
  }
  if (ev.kind === "human_approval" || ev.kind === "human_rejection") {
    const ok = ev.kind === "human_approval";
    append(`<div class="ev"><span class="av" style="--c:${ok ? "#047857" : "#7B5E68"}"><i data-lucide="${ok ? "badge-check" : "circle-x"}"></i></span><div class="body">
      <div class="who"><b>${esc(ev.officer)}</b> <span>role:aml-officer</span><span class="t">${rel(run, ev)}</span></div>
      <div class="thought ${ok ? "ok" : ""}">${ok ? "Approved" : "Rejected"} <span class="mono">${esc(ev.tool)}</span> (${esc(ev.action_id)})${ok ? " — Policy Gateway: role:aml-officer → ALLOW" : ""}. Signed and written to the immutable audit trail.</div></div></div>`);
  }
}

async function afterDecision(run) {
  paintOfficer();
  refreshHitl(run);
  renderBoard(run, { animate: false });
  await poll(run.case_id, true);
  renderInbox(); renderTicker();
}

function refreshHitl(run) {
  const html = actionsHtml(run);
  $$("[data-hitl] .acts").forEach((el) => { el.innerHTML = html; bindActionButtons(el.parentElement, run, () => afterDecision(run)); });
  bindActionButtons($("#pane-actions"), run, () => afterDecision(run));
  icons();
}

async function ask(q) {
  q = (q || "").trim();
  const run = S.active && S.runs[S.active];
  if (!q || !run || !run.done) return;
  $("#copilot-q").value = "";
  $("#copilot-send").disabled = true;
  try {
    const p = api("/api/ops/copilot", { case_id: run.case_id, question: q });
    setTimeout(() => poll(run.case_id, true), 300);
    await p;
    await poll(run.case_id, true);
  } catch (e) { toast(e.message, "error"); }
  finally { $("#copilot-send").disabled = false; }
}

// ---------------- ticker ----------------
function renderTicker() {
  const runs = Object.values(S.runs);
  const res = runs.filter((r) => r.done && r.result).map((r) => r.result);
  const pend = res.filter((r) => r.status === "PENDING_APPROVAL");
  const traced = pend.reduce((a, r) => a + r.ring.summary.victim_loss, 0);
  const remain = pend.reduce((a, r) => a + r.ring.summary.est_remaining, 0);
  const awaiting = pend.reduce((a, r) => a + (r.actions || []).filter((x) => /CHỜ|CẦN/.test(x.status)).length, 0);
  const t = (v, l, c = "") => `<div class="tick"><div class="v" style="${c ? `color:${c}` : ""}">${v}</div><div class="l">${l}</div></div>`;
  $("#ticker").innerHTML = t(S.inbox.length, "Threats received") + t(runs.filter((r) => !r.done).length, "Under investigation", "#A16207")
    + t(pend.length, "Mule rings mapped", "#BE123C") + t(vndShort(traced), "Victim funds traced") + t(vndShort(remain), "Recoverable (still in ring)", "#047857")
    + t(res.filter((r) => r.status === "CLEARED").length, "False positives auto-closed", "#047857") + t(awaiting, "Actions awaiting you", awaiting ? "#7A1238" : "");
}

export function editOfficer() {
  openModal({
    title: "Duty AML officer", confirm: "Save",
    body: `<p class="m-0">Approvals are signed with this name and written to the immutable audit trail.</p>
      <label class="text-[12px] font-semibold">Full name<input id="m-officer" class="input mt-1" value="${esc(officerName())}" autocomplete="off" required></label>`,
    onSubmit: async () => {
      const n = $("#m-officer").value.trim();
      if (!n) throw new Error("Name is required.");
      setOfficerName(n);
      paintOfficer();
    },
  });
}

export function paintOfficer() {
  const n = officerName();
  $("#analyst-name").textContent = n || "Set officer name";
  $("#analyst-initials").textContent = n ? n.split(/\s+/).map((w) => w[0]).slice(-2).join("").toUpperCase() : "PC";
}
