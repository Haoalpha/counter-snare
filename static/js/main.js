// COUNTER-SNARE bootstrap: telemetry header, tab routing, lazy module init
import { $, $$, api, esc, icons, state, toast } from "./core.js";
import { initInvestigation } from "./investigation.js";
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
  const m = state.meta;
  const chip = (icon, html, cls = "") => `<span class="flex items-center gap-1.5 rounded-lg border border-slate-800/80 bg-slate-900/70 px-2.5 py-1 ${cls}"><i data-lucide="${icon}" class="h-3.5 w-3.5"></i>${html}</span>`;
  $("#telemetry").innerHTML =
    chip("cpu", m.llm_enabled ? `MaaS · <b class="text-slate-200">${m.llm_models.length} models</b> · RPM-guarded` : `MaaS · <b class="text-amber-300">offline template mode</b>`, "text-slate-400") +
    chip("database", `Memory · <b class="text-slate-200">${esc(m.memory_backend === "AgentBase Memory" ? "AgentBase" : "local")}</b>`, "text-slate-400") +
    chip("hard-drive", `Ledger · <b class="text-slate-200">${m.world.accounts.toLocaleString()} accts · ${m.world.transactions.toLocaleString()} tx</b> <span class="text-slate-500">(synthetic)</span>`, "text-slate-400");

  $$(".tab-btn").forEach((b) => b.onclick = () => {
    $$(".tab-btn").forEach((x) => x.classList.toggle("active", x === b));
    $$(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.id !== b.dataset.tab));
    const init = LAZY[b.dataset.tab];
    if (init) Promise.resolve().then(init).catch((e) => toast(e.message, "error"));
  });
  initInvestigation();
  icons();
}

boot();
