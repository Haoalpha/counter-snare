// COUNTER-SNARE bootstrap: tab routing, lazy module init
import { $, $$, api, icons, state, toast } from "./core.js";
import { editOfficer, initOps, paintOfficer } from "./ops.js";
import { initArena } from "./arena.js";
import { initTriage } from "./triage.js";
import { initGovernance } from "./governance.js";

const LAZY = { "tab-arena": initArena, "tab-triage": initTriage, "tab-governance": initGovernance };

async function boot() {
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    toast("Backend unreachable: " + e.message, "error");
    return;
  }
  $$(".tab-btn").forEach((b) => b.onclick = () => {
    $$(".tab-btn").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", x === b ? "true" : "false"); });
    $$(".tab-panel").forEach((p) => { p.hidden = p.id !== b.dataset.tab; });
    const init = LAZY[b.dataset.tab];
    if (init) Promise.resolve().then(init).catch((e) => toast(e.message, "error"));
  });
  $("#analyst-chip").onclick = editOfficer;
  paintOfficer();
  await initOps();
  icons();
}

boot();
