// Policy Interceptor modal: the agent's own request is evaluated by the Policy Gateway (first match wins);
// a DENY forces Human-in-the-Loop sign-off by an AML Compliance Officer (real /api/approve call).
import { $, api, esc, icons, state, toast, TOOL_EN } from "./core.js";

const ACTION_ID = { delay_transactions: "A1", submit_str: "A2", freeze_account: "A4" };

export function openInterceptor(tool, verdict, caseData, onApproved) {
  const t = TOOL_EN[tool] || { label: tool, legal: "" };
  const st = verdict.matched_statement || {};
  const denied = verdict.effect !== "ALLOW";
  $("#modal-title").textContent = denied ? "POLICY INTERCEPTOR — FIRST MATCH WINS: DENY" : "POLICY GATEWAY — ALLOW";
  $("#modal-body").innerHTML = `
    <div class="rounded-lg border border-slate-800 bg-slate-900/70 p-3 font-mono text-[12px] leading-relaxed">
      <div><span class="text-slate-500">principal</span> <span class="text-cyan-300">agent:bay-nguoc</span> <span class="text-slate-500">(autonomous AI agent)</span></div>
      <div><span class="text-slate-500">tool     </span> <span class="text-amber-300">${esc(tool)}</span></div>
      <div><span class="text-slate-500">matched  </span> <span class="text-slate-300">${esc(st.principal || "*")} / ${esc(st.tool || "*")}</span> → <span class="font-bold text-rose-400">${esc(verdict.effect)}</span></div>
      <div><span class="text-slate-500">policy   </span> <span class="text-slate-300">${esc(state.meta.policy_group.name)}</span></div>
    </div>
    <p>The Policy Gateway <b class="text-rose-300">hard-blocks autonomous ${esc(t.label.toLowerCase())}</b> by the AI agent — enforced at the tool-gateway layer, not by a prompt.</p>
    <p class="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[12.5px] text-slate-300"><span class="text-slate-500">Căn cứ pháp lý:</span> ${esc(t.legal)}</p>
    <p class="font-semibold text-amber-300">Human-in-the-Loop Required: only an authorized AML Compliance Officer can approve this action.</p>
    <form id="signoff" class="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-amber-300">Compliance Officer sign-off</div>
      <input id="officer-name" class="input" placeholder="Officer full name" autocomplete="off" required>
      ${tool === "freeze_account" ? `<input id="authority-decision" class="input" placeholder="Competent-authority decision No. (required, Art. 45)" autocomplete="off">` : ""}
      <label class="flex items-start gap-2 text-[12px] text-slate-400"><input id="attest" type="checkbox" class="mt-0.5 accent-amber-500">
        I have reviewed the Evidence Vault and the STR draft for case <span class="font-mono text-slate-300">${esc(caseData.case_id)}</span>.</label>
      <div id="signoff-error" class="hidden rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-[12px] text-rose-200"></div>
      <div class="flex justify-end gap-2 pt-1">
        <button type="button" id="signoff-cancel" class="btn btn-ghost">Keep blocked</button>
        <button type="submit" class="btn btn-primary"><i data-lucide="pen-line" class="h-4 w-4"></i>Approve as Compliance Officer</button>
      </div>
    </form>`;
  const m = $("#modal");
  m.classList.remove("hidden"); m.classList.add("flex");
  icons();
  setTimeout(() => $("#officer-name").focus(), 50);
  const close = () => { m.classList.add("hidden"); m.classList.remove("flex"); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  $("#modal-close").onclick = close;
  $("#signoff-cancel").onclick = close;
  $("#signoff").onsubmit = async (e) => {
    e.preventDefault();
    const err = $("#signoff-error");
    err.classList.add("hidden");
    if (!$("#attest").checked) { err.textContent = "Please attest that you reviewed the evidence."; err.classList.remove("hidden"); return; }
    try {
      const r = await api("/api/approve", {
        case_id: caseData.case_id, action_id: ACTION_ID[tool], officer: $("#officer-name").value,
        authority_decision: $("#authority-decision") ? $("#authority-decision").value : "",
      });
      const act = (caseData.actions || []).find((a) => a.id === r.action.id);
      if (act) act.status = r.action.status;
      const li = document.createElement("li");
      li.className = "rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2 fade-in";
      li.innerHTML = `<span class="font-mono text-[11px] text-slate-500">${new Date().toLocaleTimeString()}</span> · <b class="text-emerald-300">${esc(t.label)}</b>
        approved by <b>${esc($("#officer-name").value)}</b><div class="text-[11px] text-slate-500">${esc(t.legal)}</div>`;
      const log = $("#hitl-log"); if (log.querySelector(".placeholder")) log.innerHTML = ""; log.prepend(li);
      close();
      onApproved && onApproved();
      toast(`${t.label}: approved by officer and written to the audit trail.`);
    } catch (ex) { err.textContent = ex.message; err.classList.remove("hidden"); }
  };
}
