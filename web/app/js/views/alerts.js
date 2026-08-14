/* Alerts — warnings and clearances in one thread.
 *
 * Both belong here. A system that reports blockages and never reports clearances trains
 * people to ignore it, so a clearance is not a lesser message tucked away elsewhere — it
 * sits in the same list, distinguished by colour and wording rather than by location.
 */

import { api } from "../api.js";
import { refreshNotifications, state, subscribe } from "../store.js";
import { ago, empty, errorState, esc, icon, skeleton, toast } from "../ui.js";

// A clearance carries zero confidence and its wording says so. Rather than add a field
// to the API for something the message already conveys, read it from the text.
const isClearance = (n) =>
  n.confidence === 0 ||
  /cleared|could not be found|never confirmed/i.test(n.message);

export default function alertsView(mount) {
  mount.innerHTML = `
    <div class="scroll">
      <div class="pad" style="padding-bottom:8px">
        <div class="row-between">
          <h2>Your alerts</h2>
          <button class="btn btn--ghost btn--sm" id="read">Mark all read</button>
        </div>
      </div>
      <div class="pad" style="padding-top:0"><div class="list" id="list">${skeleton(4)}</div></div>
    </div>`;

  render(state.notifications);
  const unsubscribe = subscribe((s) => render(s.notifications));
  refreshNotifications().catch(showError);

  mount.querySelector("#read").addEventListener("click", async () => {
    try {
      await api("/notifications/read", { method: "POST" });
      await refreshNotifications();
      toast("Marked as read");
    } catch (err) { toast(err.message, { error: true }); }
  });

  function render(items) {
    const list = mount.querySelector("#list");
    mount.querySelector("#read").disabled = !items.some(n => !n.read_at);

    if (!items.length) {
      list.innerHTML = empty(
        "No alerts yet",
        "Follow the roads you travel and you will be warned when something blocks them.",
      );
      return;
    }

    list.innerHTML = items.map((n) => {
      const cleared = isClearance(n);
      const unread = !n.read_at;
      const dot = cleared ? "var(--green-600)" : unread ? "var(--red)" : "var(--faint)";
      return `
        <div class="inline" style="align-items:flex-start;gap:10px;
             ${unread ? "background:var(--grey-100);margin:0 -16px;padding:12px 16px" : ""}">
          <span style="width:7px;height:7px;border-radius:50%;background:${dot};flex:none;margin-top:7px"></span>
          <span class="grow">
            <span class="t" style="font-weight:${unread ? 500 : 400}">${esc(n.message)}</span>
            <span class="m">${esc(ago(n.created_at))}${cleared ? " · cleared" : ""}</span>
          </span>
        </div>`;
    }).join("");
  }

  function showError(err) {
    mount.querySelector("#list").innerHTML = errorState(err.message, "retry");
    mount.querySelector('[data-action="retry"]')
      ?.addEventListener("click", () => refreshNotifications().catch(showError));
  }

  return { destroy: unsubscribe };
}
