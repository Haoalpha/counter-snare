// TAB 2 — Red Arena: adversarial planning–execution simulation, evolution table, live engagement console
import { $, api, busy, esc, icons, pct, toast, TYPOLOGY_EN } from "./core.js";

let loaded = false;
const LEVEL = { de: "Easy — known tactics", vua: "Medium — partial concealment", kho: "Hard — deliberate evasion" };

export async function initArena() {
  $("#btn-arena").onclick = launch;
  if (loaded) return;
  const ev = await api("/api/eval");
  loaded = true;
  const al = ev.account_level;
  const k = (v, l) => `<div class="kpi"><div class="v text-emerald-700">${v}</div><div class="l">${l}</div></div>`;
  $("#eval-kpis").innerHTML = k(al.auc_roc.toFixed(3), "AUC-ROC") + k(pct(al["precision@0.5"]), "Precision") + k(pct(al["recall@0.5"]), `Recall · ${al.n_mules} mules`);
  const rows = Object.entries(ev.arena).map(([lvl, v]) => {
    const d1 = v.v1.ring_recall_mean, d2 = v.v2.ring_recall_mean;
    const cell = (x) => `<div class="flex items-center gap-2"><div class="bar-track w-28"><div class="bar-fill" style="width:${x * 100}%;background:${x >= 0.8 ? "#059669" : x >= 0.4 ? "#d97706" : "#be123c"}"></div></div><span class="font-mono font-semibold">${pct(x)}</span></div>`;
    const tactic = { de: "Fast pass-through, sub-10M structuring, shared devices", vua: "Holding 20 min – 3 h, mixed structuring, more devices", kho: "Holding 4 – 33 hours, no structuring, no shared devices, aged accounts" }[lvl];
    return `<tr><td><span class="badge ${lvl === "kho" ? "b-rose" : lvl === "vua" ? "b-amber" : "b-emerald"}">${esc(LEVEL[lvl])}</span></td><td class="text-[12px] text-muted">${tactic}</td>
      <td>${cell(d1)}</td><td>${cell(d2)}</td><td class="font-mono">${v.v1.fp_accounts_mean} → ${v.v2.fp_accounts_mean}</td></tr>`;
  });
  $("#evolution").innerHTML = `<tr><th>Adversary level</th><th>Evasion tactics</th><th>v1 Baseline Model</th><th>v2 Self-Evolved Model</th><th>False positives / ~${ev.arena.de.v2.normal_accounts} accts</th></tr>` + rows.join("");
  $("#ring-eval").innerHTML = `<tr><th>Campaign</th><th>Typology</th><th>Seen in training</th><th>Mules found</th><th>Victims found</th></tr>` +
    ev.ring_level.map((r) => `<tr><td class="font-mono">${esc(r.campaign_id)}</td><td>${esc(TYPOLOGY_EN[r.typology] || r.typology)}</td>
      <td>${r.seen_in_training ? '<span class="badge b-slate">yes</span>' : '<span class="badge b-amber">NO · novel</span>'}</td>
      <td class="font-mono">${r.found}/${r.mules}${r.extra ? ` (+${r.extra})` : ""}</td><td class="font-mono">${r.victims_found}/${r.victims}</td></tr>`).join("");
  icons();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function line(html) {
  const t = $("#terminal");
  t.insertAdjacentHTML("beforeend", "\n" + html);
  t.scrollTop = t.scrollHeight;
}
const ts = () => `<span class="d">[${new Date().toLocaleTimeString()}]</span>`;

async function launch() {
  const diff = $("#arena-diff").value, useLlm = $("#arena-llm").checked;
  const b = $("#btn-arena");
  busy(b, true, "Engagement running…");
  $("#terminal").innerHTML = `counter-snare@red-arena:~$ engage --level ${diff} --planner ${useLlm ? "llm" : "random"}`;
  line(`${ts()} <span class="r">RED</span>  requesting evasion campaign plan${useLlm ? " from Red-Team LLM (GreenNode MaaS)" : " (constrained random planner)"} · level: ${esc(LEVEL[diff])}`);
  line(`${ts()} <span class="y">SIM</span>  provisioning synthetic world (≈700 customers, 30 days) …`);
  const t0 = Date.now();
  try {
    const r = await api("/api/arena", { difficulty: diff, use_llm: useLlm });
    if (r.llm_rationale) { await sleep(250); line(`${ts()} <span class="r">RED</span>  strategy ▸ "${esc(r.llm_rationale)}"`); }
    for (const c of r.campaigns) {
      await sleep(260);
      line(`${ts()} <span class="r">RED</span>  campaign ${esc(c.campaign_id)} · ${esc(c.planner === "LLM Red Team" ? "LLM-planned" : "random-constrained")} · ${esc(TYPOLOGY_EN[c.typology_key] || c.typology)}`);
      line(`         <span class="d">mules=${c.mules} holding=${c.dwell_minutes.join("–")}min structuring=${c.structuring ? "yes" : "no"} devices=${c.shared_devices}</span>`);
    }
    await sleep(300);
    line(`${ts()} <span class="y">SIM</span>  executed plans → labelled transactions (seed ${r.seed})`);
    line(`${ts()} <span class="b">BLUE</span> hunting rings from one seed account each …`);
    for (const c of r.campaigns) {
      await sleep(240);
      const ok = c.caught_via_ring === c.mules;
      line(`${ts()} <span class="b">BLUE</span> ${esc(c.campaign_id)} → <span class="${ok ? "g" : "r"}">${c.caught_via_ring}/${c.mules} mules recovered</span>${c.false_extra ? ` <span class="y">(+${c.false_extra} extra)</span>` : ""}`);
    }
    await sleep(250);
    line(`${ts()} <span class="${r.ring_recall >= 0.8 ? "g" : "r"}">RESULT</span> ring detection ${pct(r.ring_recall)} · false positives ${r.false_positive_accounts}/${r.normal_accounts} normal accounts · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    line(r.ring_recall < 1 ? `${ts()} <span class="y">EVOLVE</span> missed patterns queued as training data for the next model version` : `${ts()} <span class="g">EVOLVE</span> defender held — no new blind spot found this round`);
  } catch (e) { line(`${ts()} <span class="r">ERROR</span> ${esc(e.message)}`); toast(e.message, "error"); }
  finally { busy(b, false); }
}
