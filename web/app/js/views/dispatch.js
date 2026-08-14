/* Dispatch — the control room, and the warden's own list.
 *
 * One view serving two roles, because they are two ends of the same loop: an officer
 * decides who goes, a warden goes and says what they found. Each sees only their half.
 *
 * The refusals here are the state machine, not validation. An incident below 0.70 cannot
 * be assigned, and one nobody was sent to cannot be resolved — so the interface does not
 * offer either. A button that would be refused should never appear.
 */

import { api } from "../api.js";
import { refreshIncidents, role, state } from "../store.js";
import {
  LABEL, TYPE_LABEL, ago, avatar, closeSheet, empty, errorState, esc, icon,
  pct, sheet, skeleton, stats as statTiles, toast,
} from "../ui.js";

export default function dispatchView(mount) {
  const isWarden = role() === "warden";

  mount.innerHTML = `
    <div class="scroll pad stack">
      ${isWarden ? "" : `
        <div class="card">
          <h2>Today</h2>
          <div id="stats">${skeleton(1)}</div>
        </div>`}
      <div class="card">
        <h2>${isWarden ? "Assigned to you" : "Dispatch queue"}</h2>
        <div class="list" id="queue">${skeleton(3)}</div>
        <p class="hint" style="margin-top:10px">
          ${isWarden
            ? `Resolving updates the ${LABEL.reputation.toLowerCase()} of everyone who reported it, so say what you actually found.`
            : "Only incidents above 70% accuracy appear here. That is the escalation threshold — below it, the answer is more corroboration, not a lower bar."}
        </p>
      </div>
    </div>`;

  load();

  async function load() {
    try {
      if (isWarden) {
        renderQueue(await api("/incidents/assigned/mine"), []);
      } else {
        const [queue, wardens, stats] = await Promise.all([
          api("/incidents/queue"),
          api("/incidents/wardens/available"),
          api("/admin/stats").catch(() => null),   // officers cannot read stats; that is fine
        ]);
        renderStats(queue, stats);
        renderQueue(queue, wardens);
      }
    } catch (err) {
      mount.querySelector("#queue").innerHTML = errorState(err.message, "retry");
      mount.querySelector('[data-action="retry"]')?.addEventListener("click", load);
    }
  }

  function renderStats(queue, stats) {
    const box = mount.querySelector("#stats");
    if (!box) return;
    const awaiting = queue.filter(i => i.status === "verified").length;
    const assigned = queue.filter(i => i.status === "assigned").length;
    box.innerHTML = statTiles([
      [awaiting, "awaiting a warden"],
      [assigned, "being attended"],
      ...(stats ? [[stats.reports, "reports held"]] : []),
    ]);
  }

  function renderQueue(items, wardens) {
    const box = mount.querySelector("#queue");
    if (!items.length) {
      box.innerHTML = isWarden
        ? empty("Nothing assigned", "An officer will send you where you are needed.")
        : empty("Nothing needs a warden", "Incidents appear here once accuracy reaches 70%.");
      return;
    }

    const options = wardens.map(w =>
      `<option value="${esc(w.id)}">${esc(w.display_name)}</option>`).join("");

    box.innerHTML = items.map(i => `
      <div>
        <div class="row-between">
          <span class="grow">
            <span class="t">${esc(TYPE_LABEL[i.incident_type] ?? i.incident_type)}</span>
            <span class="m">${i.report_count} reports · ${LABEL.confidence.toLowerCase()} ${pct(i.confidence)}
              · ${esc(ago(i.last_reported_at))}</span>
          </span>
          <span class="tag tag--${esc(i.status)}">${esc(i.status.replace("_"," "))}</span>
        </div>
        <div class="inline" style="margin-top:10px">
          <button class="btn btn--ghost btn--sm" data-evidence="${esc(i.id)}">Evidence</button>
          ${i.status === "verified" && !isWarden ? `
            <select class="input" style="width:auto;min-height:34px;padding:5px 10px;font-size:13px"
                    id="w_${esc(i.id)}" aria-label="Choose a warden">${options}</select>
            <button class="btn btn--sm" data-assign="${esc(i.id)}">Send warden</button>` : ""}
          ${i.status === "assigned" ? `
            <button class="btn btn--sm" data-resolve="${esc(i.id)}" data-outcome="confirmed">Road now clear</button>
            <button class="btn btn--ghost btn--sm" data-resolve="${esc(i.id)}" data-outcome="false_alarm">Nothing there</button>
            ${isWarden ? "" : `<button class="btn btn--ghost btn--sm" data-unassign="${esc(i.id)}">Recall</button>`}` : ""}
        </div>
      </div>`).join("");

    box.querySelectorAll("[data-evidence]").forEach(b =>
      b.addEventListener("click", () => showEvidence(b.dataset.evidence)));
    box.querySelectorAll("[data-assign]").forEach(b =>
      b.addEventListener("click", () => assign(b, b.dataset.assign)));
    box.querySelectorAll("[data-unassign]").forEach(b =>
      b.addEventListener("click", () => unassign(b, b.dataset.unassign)));
    box.querySelectorAll("[data-resolve]").forEach(b =>
      b.addEventListener("click", () => confirmResolve(b.dataset.resolve, b.dataset.outcome)));
  }

  async function assign(btn, id) {
    const select = mount.querySelector(`#w_${CSS.escape(id)}`);
    btn.disabled = true;
    try {
      await api(`/incidents/${id}/assign`, {
        method: "POST", body: JSON.stringify({ warden_id: select.value }),
      });
      toast("Warden sent");
      await Promise.all([load(), refreshIncidents()]);
    } catch (err) { toast(err.message, { error: true }); btn.disabled = false; }
  }

  async function unassign(btn, id) {
    btn.disabled = true;
    try {
      await api(`/incidents/${id}/unassign`, { method: "POST" });
      toast("Warden recalled — the incident is back in the queue");
      await Promise.all([load(), refreshIncidents()]);
    } catch (err) { toast(err.message, { error: true }); btn.disabled = false; }
  }

  /* Resolving moves reputations, so it is confirmed rather than fired on one tap —
     and the confirmation says what the consequence is. */
  function confirmResolve(id, outcome) {
    const confirmed = outcome === "confirmed";
    sheet({
      title: confirmed ? "Road now clear?" : "Nothing there?",
      body: `
        <p>${confirmed
          ? "You attended and the road is passable again."
          : "You attended and found nothing blocking the road."}</p>
        <p class="hint" style="margin-top:12px">
          ${confirmed
            ? "Everyone who reported this will have their credibility raised, and anyone warned about it will be told the road is clear."
            : "Everyone who reported this will have their credibility lowered. Use this when the report was mistaken, not when the problem cleared before you arrived — for that, choose “road now clear”."}
        </p>
        <div class="field" style="margin-top:16px">
          <label for="rn">Note <span class="faint">· optional</span></label>
          <textarea class="input" id="rn" maxlength="500"
                    placeholder="${confirmed ? "Vehicle recovered, both lanes open" : "Attended, road was clear on arrival"}"></textarea>
        </div>`,
      footer: `<button class="btn btn--block" id="go">${confirmed ? "Confirm the road is clear" : "Record as a false alarm"}</button>`,
      onMount: (el) => {
        el.querySelector("#go").addEventListener("click", async () => {
          const btn = el.querySelector("#go");
          btn.disabled = true; btn.textContent = "Recording…";
          try {
            const res = await api(`/incidents/${id}/resolve`, {
              method: "POST",
              body: JSON.stringify({ resolution: outcome, note: el.querySelector("#rn").value.trim() || null }),
            });
            closeSheet();
            const moved = res.reputations_updated
              .map(r => `${r.display_name} → ${pct(r.reputation)}`).join(", ");
            toast(moved ? `Closed. Credibility updated: ${moved}` : "Closed.");
            await Promise.all([load(), refreshIncidents()]);
          } catch (err) {
            toast(err.message, { error: true });
            btn.disabled = false;
            btn.textContent = confirmed ? "Confirm the road is clear" : "Record as a false alarm";
          }
        });
      },
    });
  }

  async function showEvidence(id) {
    sheet({
      title: "Evidence",
      body: `<div class="list">${skeleton(4)}</div>`,
      onMount: async (el) => {
        const body = el.querySelector(".sheet__body");
        try {
          const inc = await api(`/incidents/${id}`);
          const atts = await api(`/reports/${inc.evidence[0]?.report_id}/attachments`).catch(() => []);
          body.innerHTML = `
            <div class="inline" style="margin-bottom:14px">
              <span class="bar grow"><i style="width:${Math.floor(inc.confidence*100)}%"></i></span>
              <strong class="num">${pct(inc.confidence)}</strong>
            </div>
            ${atts.length ? `
              <div class="card card--flat" style="margin-bottom:14px">
                <div class="inline">${icon("mic",16)}
                  <span class="grow"><span class="t" style="font-size:13px">Recording from the reporter</span>
                  <span class="m">${atts[0].duration_seconds ? Math.round(atts[0].duration_seconds)+"s" : ""}</span></span>
                  <a class="btn btn--ghost btn--sm" href="${esc(atts[0].url)}" target="_blank" rel="noopener">Play</a>
                </div>
              </div>` : ""}
            <h3 style="margin-bottom:6px">Who reported it</h3>
            <div class="list">
              ${inc.evidence.map(e => `
                <div class="row-between">
                  <span class="inline">${avatar(e.reporter_name, e.report_id, 28)}
                    <span><span class="t" style="font-size:13px">${esc(e.reporter_name)}</span>
                    <span class="m">${LABEL.reputation.toLowerCase()} ${pct(e.reporter_reputation)} · ${esc(ago(e.occurred_at))}</span></span>
                  </span>
                  <span class="num" style="font-size:13px">${pct(e.weight / 0.45)}</span>
                </div>`).join("")}
            </div>`;
        } catch (err) {
          body.innerHTML = errorState(err.message);
        }
      },
    });
  }

  return { destroy() { closeSheet(); } };
}
