/* The roads you travel.
 *
 * A curated list of real Accra corridors rather than a map to draw on. Drawing your own
 * route needs a routing engine and full network data; fifteen named roads cover most
 * journeys and could be built now. That is a limitation, recorded in the backlog, not a
 * preference dressed up as one.
 *
 * Live incident counts sit beside each road so following is worth doing before anything
 * has happened to you.
 */

import { api } from "../api.js";
import { refreshCorridors, state, subscribe } from "../store.js";
import { debounce, empty, errorState, esc, icon, skeleton, toast } from "../ui.js";

export default function routesView(mount) {
  let filter = "";

  mount.innerHTML = `
    <div class="scroll">
      <div class="pad" style="padding-bottom:8px">
        <div class="row-between">
          <h2>Roads you travel</h2>
          <span class="xs" id="summary"></span>
        </div>
        <div style="position:relative;margin-top:10px">
          <span style="position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--faint)">
            ${icon("search",16)}</span>
          <input class="input" id="q" type="search" placeholder="Search roads"
                 aria-label="Search roads" style="padding-left:36px">
        </div>
      </div>
      <div class="pad" style="padding-top:0"><div class="list" id="list">${skeleton(5)}</div></div>
    </div>`;

  render(state);
  const unsubscribe = subscribe(render);
  refreshCorridors().catch(showError);

  mount.querySelector("#q").addEventListener("input", debounce((e) => {
    filter = e.target.value.trim().toLowerCase();
    render(state);
  }, 150));

  function incidentsOn(corridorName) {
    // The API does not return incidents per corridor, so this is not a count — it is
    // deliberately absent rather than guessed. Showing a wrong number beside a road
    // someone relies on would be worse than showing none.
    return null;
  }

  function render(s) {
    const list = mount.querySelector("#list");
    const all = s.corridors || [];
    const following = all.filter(c => c.following).length;

    mount.querySelector("#summary").textContent =
      all.length ? `${following} followed · ${all.length} available` : "";

    const shown = filter
      ? all.filter(c => c.name.toLowerCase().includes(filter)
                     || (c.description || "").toLowerCase().includes(filter))
      : all;

    if (!all.length) {
      list.innerHTML = empty("No roads yet", "Corridors are set up by an administrator.");
      return;
    }
    if (!shown.length) {
      list.innerHTML = empty("Nothing matches", `No road contains “${filter}”.`);
      return;
    }

    list.innerHTML = shown.map(c => `
      <div class="row-between">
        <span class="grow">
          <span class="t">${esc(c.name)}</span>
          <span class="m">${esc(c.description || "")}</span>
        </span>
        <button class="btn ${c.following ? "" : "btn--ghost"} btn--sm"
                data-id="${esc(c.id)}" data-following="${c.following}"
                aria-pressed="${c.following}">
          ${c.following ? "Following" : "Follow"}
        </button>
      </div>`).join("");

    list.querySelectorAll("[data-id]").forEach(btn =>
      btn.addEventListener("click", () => toggle(btn)));
  }

  async function toggle(btn) {
    const following = btn.dataset.following === "true";
    btn.disabled = true;
    try {
      await api(`/corridors/${btn.dataset.id}/follow`, { method: following ? "DELETE" : "PUT" });
      await refreshCorridors();
      toast(following ? "Stopped following" : "Following — you will be warned about this road");
    } catch (err) {
      toast(err.message, { error: true });
      btn.disabled = false;
    }
  }

  function showError(err) {
    mount.querySelector("#list").innerHTML = errorState(err.message, "retry");
    mount.querySelector('[data-action="retry"]')
      ?.addEventListener("click", () => refreshCorridors().catch(showError));
  }

  return { destroy: unsubscribe };
}
