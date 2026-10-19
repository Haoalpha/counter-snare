// COUNTER-SNARE bootstrap: runtime status pills, tab routing, lazy module init
import { $, $$, api, esc, icons, state, toast } from "./core.js";
import { editOfficer, initOps, paintOfficer } from "./ops.js";
import { initArena } from "./arena.js";
import { initTriage } from "./triage.js";
import { initGovernance } from "./governance.js";

const LAZY = { "tab-arena": initArena, "tab-triage": initTriage, "tab-governance": initGovernance };

async function pills() {
  const m = state.meta;
  let st = null;
  try { st = await api("/api/ops/status"); } catch (e) { /* keep last */ }
  const used = st ? Object.values(st.rate_limits).reduce((a, v) => a + v.used_last_60s, 0) : 0;
  const lim = st ? Object.values(st.rate_limits).reduce((a, v) => a + (v.limit_rpm || 0), 0) : 0;
  const onAB = m.runtime.platform !== "local";
  $("#status-pills").innerHTML =
    `<span class="pill"><span class="dot"></span>${onAB ? "GreenNode AgentBase" : "Local runtime"} · <b>ACTIVE</b></span>` +
    `<span class="pill"><span class="dot ${m.llm_enabled ? "" : "warn"}"></span>MaaS · <b>${m.llm_enabled ? `${m.llm_models.length} models · ${used}/${lim} RPM` : "offline template mode"}</b></span>` +
    `<span class="pill"><span class="dot ${m.memory_backend === "AgentBase Memory" ? "" : "warn"}"></span>Memory · <b>${esc(m.memory_backend === "AgentBase Memory" ? "AgentBase" : "local")}</b></span>` +
    `<span class="pill">Ledger · <b>${m.world.accounts.toLocaleString()} accts · ${m.world.transactions.toLocaleString()} tx</b> (synthetic)</span>`;
}

async function boot() {
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    toast("Backend unreachable: " + e.message, "error");
    return;
  }
  pills();
  setInterval(pills, 5000);
  $$(".tab-btn").forEach((b) => b.onclick = () => {
    $$(".tab-btn").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", x === b ? "true" : "false"); });
    $$(".tab-panel").forEach((p) => { p.hidden = p.id !== b.dataset.tab; });
    $("#ticker").hidden = b.dataset.tab !== "tab-ops";
    const init = LAZY[b.dataset.tab];
    if (init) Promise.resolve().then(init).catch((e) => toast(e.message, "error"));
  });
  $("#analyst-chip").onclick = editOfficer;
  paintOfficer();
  await initOps();
  icons();
}

boot();
