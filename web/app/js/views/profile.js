/* Profile: who you are, how trusted you are, and what you have filed.
 *
 * Reputation gates whether your reports reach the police, so it is explained rather than
 * displayed. A number that decides something on your behalf and cannot be understood is
 * a number people learn to resent.
 */

import { api, auth } from "../api.js";
import { go } from "../router.js";
import { loadUser, signOut, state } from "../store.js";
import {
  LABEL, ago, avatar, empty, errorState, esc, icon, pct, rules, sheet, closeSheet,
  skeleton, stats as statTiles, toast, validate,
} from "../ui.js";

export default function profileView(mount) {
  const user = state.user;
  if (!user) { go("/signin", { replace: true }); return { destroy() {} }; }

  const total = user.reports_confirmed + user.reports_contradicted;

  mount.innerHTML = `
    <div class="scroll">
      <div style="background:var(--green);color:#fff;padding:20px 16px">
        <div class="inline" style="gap:12px">
          ${avatar(user.display_name, user.id, 48)}
          <div>
            <div style="font-size:18px;font-weight:600">${esc(user.display_name)}</div>
            <div style="font-size:13px;opacity:.85">${esc(user.role).toUpperCase()} · joined ${esc(new Date(user.created_at).toLocaleDateString("en-GB",{month:"long",year:"numeric"}))}</div>
          </div>
        </div>
      </div>

      <div class="pad stack">
        <div class="card">
          <div class="row-between">
            <h2 style="margin:0">Your ${LABEL.reputation.toLowerCase()}</h2>
            <strong class="num" style="font-size:20px">${pct(user.reputation)}</strong>
          </div>
          <div class="bar" style="margin:10px 0"><i style="width:${Math.floor(user.reputation*100)}%"></i></div>
          <div style="margin-top:12px">${statTiles([
            [user.reports_confirmed, "confirmed"],
            [user.reports_contradicted, "not found", "bad"],
          ])}</div>
          <p class="hint" style="margin-top:12px">
            Your credibility rises when a warden confirms something you reported, and falls when
            one attends and finds nothing. It decides how much weight your reports carry —
            reaching 90% takes around eighteen confirmations, so it is slow to build and
            meaningful when built.
          </p>
        </div>

        <div class="card">
          <h2>Account</h2>
          <dl class="deets" style="margin:0">
            <div class="deet">
              <dt>Display name</dt>
              <dd>${esc(user.display_name)}</dd>
              <button class="btn btn--ghost btn--icon deet__act" id="editName"
                      aria-label="Edit your display name" title="Edit display name">
                ${icon("pencil",17)}</button>
            </div>
            <div class="deet">
              <dt>Email</dt>
              <dd class="muted">${esc(user.email)}</dd>
              <span class="tag tag--reported deet__act">locked</span>
            </div>
            <div class="deet">
              <dt>Password</dt>
              <dd class="muted">••••••••</dd>
              <button class="btn btn--ghost btn--icon deet__act" id="editPass"
                      aria-label="Change your password" title="Change password">
                ${icon("key",17)}</button>
            </div>
          </dl>
          <p class="hint" style="margin-top:10px">
            Your email is how you sign in. Changing it would need a verification message this
            system cannot send yet, so it is fixed — ask an administrator if it is wrong.
          </p>
        </div>

        <div class="card">
          <h2>Your reports</h2>
          <div id="reports">${skeleton(3)}</div>
        </div>

        <button class="btn btn--danger btn--block" id="out">${icon("logout",16)} Sign out</button>
      </div>
    </div>`;

  loadReports();

  mount.querySelector("#editName").addEventListener("click", editName);
  mount.querySelector("#editPass").addEventListener("click", editPassword);
  mount.querySelector("#out").addEventListener("click", () => {
    signOut(); toast("Signed out"); go("/");
  });

  async function loadReports() {
    const box = mount.querySelector("#reports");
    try {
      const reports = await api("/reports/mine?limit=25");
      if (!reports.length) {
        box.innerHTML = empty("Nothing yet", "Reports you file will appear here with what came of them.");
        return;
      }
      box.innerHTML = reports.map((r, i) => `
        <div class="disc">
          <button class="disc__head" aria-expanded="false" data-open="${i}"
                  aria-controls="rep_${i}">
            <span class="t">${esc(labelFor(r.incident_type))}</span>
            <span class="inline" style="gap:var(--s2)">
              <span class="m" style="margin:0">${esc(ago(r.occurred_at))}</span>
              ${icon("chevron",16,"chev")}
            </span>
          </button>
          <div class="disc__body hide" id="rep_${i}" data-body="${i}"
               data-report-id="${esc(r.id)}">
            ${r.note
              ? `<p style="margin:0 0 10px;font-size:13.5px;line-height:1.5">\u201c${esc(r.note)}\u201d</p>`
              : `<p class="xs faint" style="margin:0 0 10px">No note was written with this report.</p>`}
            <div class="xs" style="line-height:1.7">
              <div>Filed ${esc(new Date(r.occurred_at).toLocaleString("en-GB",
                { dateStyle:"medium", timeStyle:"short" }))}</div>
              <div class="num">${r.latitude.toFixed(5)}, ${r.longitude.toFixed(5)}</div>
            </div>
            <div data-evidence="${i}" style="margin-top:10px"></div>
          </div>
        </div>`).join("");

      wireDisclosure(box);
    } catch (err) {
      box.innerHTML = errorState(err.message);
    }
  }

  /* Open one report to see what it actually carried.
   *
   * The evidence is fetched when the panel opens rather than with the list — twenty-five
   * reports would otherwise be twenty-five requests nobody asked for, on a connection
   * this system assumes is bad. Fetched once and kept, so opening and closing the same
   * report does not ask again.
   *
   * This is also the only place a reporter can confirm their own photograph or recording
   * arrived, which until now they simply had to trust. */
  function wireDisclosure(root) {
    root.querySelectorAll("[data-open]").forEach((head) => {
      const body = root.querySelector(`[data-body="${head.dataset.open}"]`);
      head.addEventListener("click", () => {
        const closed = body.classList.toggle("hide");
        head.setAttribute("aria-expanded", String(!closed));
        if (!closed) loadEvidence(body, head.dataset.open);
      });
    });
  }

  async function loadEvidence(body, index) {
    const slot = body.querySelector(`[data-evidence="${index}"]`);
    if (slot.dataset.loaded) return;
    slot.dataset.loaded = "1";
    slot.innerHTML = `<span class="xs faint">Checking what was attached…</span>`;
    try {
      const items = await api(`/reports/${body.dataset.reportId}/attachments`);
      if (!items.length) {
        slot.innerHTML = `<span class="xs faint">Nothing attached.</span>`;
        return;
      }
      slot.innerHTML = items.map(a => a.kind === "photo"
        ? `<a href="${esc(a.url)}" target="_blank" rel="noopener"
              style="display:inline-block;width:72px;height:72px;border-radius:var(--r-sm);
                     overflow:hidden;background:var(--grey-100);margin-right:8px">
             <img src="${esc(a.url)}" alt="Photograph you attached" loading="lazy"
                  style="width:100%;height:100%;object-fit:cover"></a>`
        : `<div style="margin-top:6px">
             <div class="xs" style="margin-bottom:4px">${icon("mic",13)}
               Your recording${a.is_public ? "" : " · only you and the control room"}</div>
             <audio controls preload="none" src="${esc(a.url)}"
                    style="width:100%;height:34px"></audio>
           </div>`).join("");
    } catch (err) {
      slot.innerHTML = `<span class="xs" style="color:var(--red)">${esc(err.message)}</span>`;
    }
  }

  function labelFor(t) {
    return { accident:"Accident", flood:"Flooding", closure:"Road closure",
             signal_outage:"Traffic lights out", roadworks:"Roadworks",
             surface_defect:"Damaged road surface" }[t] ?? t;
  }

  /* ------------------------------------------------------------ edit name */

  function editName() {
    sheet({
      title: "Edit your details",
      body: `
        <form id="nf" novalidate>
          <div class="field">
            <label for="dn">Display name <span class="req">*</span></label>
            <input class="input" id="dn" name="display_name" maxlength="80" value="${esc(user.display_name)}">
            <div class="hint">Shown to officers on incidents you report.</div>
            <div class="err" data-err="display_name"></div>
          </div>
          <div class="field" style="margin-top:16px">
            <label>Email</label>
            <input class="input" value="${esc(user.email)}" disabled>
            <div class="hint">Fixed — it is how you sign in.</div>
          </div>
          <div class="field" style="margin-top:16px">
            <label>Role</label>
            <input class="input" value="${esc(user.role)}" disabled>
            <div class="hint">Only an administrator can change a role. Nobody promotes themselves.</div>
          </div>
        </form>`,
      footer: `<button class="btn btn--block" id="saveName" form="nf">Save changes</button>`,
      onMount: (el) => {
        const form = el.querySelector("#nf");
        const btn = el.querySelector("#saveName");
        const v = validate(form, { display_name: rules.minLength(2, "Your name") }, btn);
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (!v.validateAll()) return;
          btn.disabled = true; btn.textContent = "Saving…";
          try {
            await api("/auth/me", {
              method: "PATCH",
              body: JSON.stringify({ display_name: form.display_name.value.trim() }),
            });
            await loadUser();
            closeSheet();
            toast("Saved");
            go("/you");
          } catch (err) {
            toast(err.message, { error: true });
            btn.disabled = false; btn.textContent = "Save changes";
          }
        });
      },
    });
  }

  /* -------------------------------------------------------- change password */

  function editPassword() {
    sheet({
      title: "Change password",
      body: `
        <form id="pf" novalidate>
          <div class="field">
            <label for="cur">Current password <span class="req">*</span></label>
            <input class="input" id="cur" name="current_password" type="password" autocomplete="current-password">
            <div class="err" data-err="current_password"></div>
          </div>
          <div class="field" style="margin-top:16px">
            <label for="np">New password <span class="req">*</span></label>
            <input class="input" id="np" name="new_password" type="password" autocomplete="new-password">
            <div class="hint">At least 8 characters, no more than 72 bytes.</div>
            <div class="err" data-err="new_password"></div>
          </div>
          <div class="field" style="margin-top:16px">
            <label for="cf">Confirm new password <span class="req">*</span></label>
            <input class="input" id="cf" name="confirm" type="password" autocomplete="new-password">
            <div class="err" data-err="confirm"></div>
          </div>
          <p class="hint" style="margin-top:16px">
            Your current password is required so that someone holding your unlocked phone
            cannot lock you out of your own account.
          </p>
        </form>`,
      footer: `<button class="btn btn--block" id="savePass" form="pf">Change password</button>`,
      onMount: (el) => {
        const form = el.querySelector("#pf");
        const btn = el.querySelector("#savePass");
        const v = validate(form, {
          current_password: rules.required("Your current password"),
          new_password: rules.password(),
          confirm: rules.matches("new_password", "These do not match"),
        }, btn);

        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (!v.validateAll()) return;
          btn.disabled = true; btn.textContent = "Changing…";
          try {
            await api("/auth/me/password", {
              method: "POST",
              body: JSON.stringify({
                current_password: form.current_password.value,
                new_password: form.new_password.value,
              }),
            });
            closeSheet();
            toast("Password changed");
          } catch (err) {
            toast(err.message, { error: true });
            btn.disabled = false; btn.textContent = "Change password";
          }
        });
      },
    });
  }

  return { destroy() { closeSheet(); } };
}
