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
  ago, avatar, empty, errorState, esc, icon, rules, sheet, closeSheet,
  skeleton, toast, validate,
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
            <h2 style="margin:0">Your standing</h2>
            <strong class="num" style="font-size:20px">${user.reputation.toFixed(2)}</strong>
          </div>
          <div class="bar" style="margin:10px 0"><i style="width:${Math.round(user.reputation*100)}%"></i></div>
          <div class="inline" style="gap:20px;margin-top:12px;text-transform:uppercase;text-align:center">
            <span><strong style="font-size:18px">${user.reports_confirmed}</strong>
              <span class="xs" style="display:block">confirmed</span></span>
            <span><strong style="font-size:18px;color:var(--red)">${user.reports_contradicted}</strong>
              <span class="xs" style="display:block">not found</span></span>
          </div>
          <p class="hint" style="margin-top:12px">
            Your standing rises when a warden confirms something you reported, and falls when
            one attends and finds nothing. It decides how much weight your reports carry —
            reaching 0.9 takes around eighteen confirmations, so it is slow to build and
            meaningful when built.
          </p>
        </div>

        <div class="card">
          <h2>Account</h2>
          <div class="list">
            <div class="row-between">
              <span><span class="xs">Display name</span><span class="t">${esc(user.display_name)}</span></span>
              <button class="btn btn--ghost btn--sm" id="editName">Edit</button>
            </div>
            <div class="row-between">
              <span><span class="xs">Email</span><span class="t muted">${esc(user.email)}</span></span>
              <span class="tag tag--reported">locked</span>
            </div>
            <div class="row-between">
              <span><span class="xs">Password</span><span class="t muted">••••••••</span></span>
              <button class="btn btn--ghost btn--sm" id="editPass">Change</button>
            </div>
          </div>
          <p class="hint" style="margin-top:10px">
            Your email is how you sign in. Changing it would need a verification message this
            system cannot send yet, so it is fixed — ask an administrator if it is wrong.
          </p>
        </div>

        <div class="card">
          <h2>Your reports</h2>
          <div class="list" id="reports">${skeleton(3)}</div>
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
      box.innerHTML = reports.map(r => `
        <div class="row-between">
          <span class="grow">
            <span class="t">${esc(labelFor(r.incident_type))}</span>
            <span class="m">${esc(ago(r.occurred_at))}${r.note ? ` · ${esc(r.note.slice(0,44))}${r.note.length>44?"…":""}` : ""}</span>
          </span>
        </div>`).join("");
    } catch (err) {
      box.innerHTML = errorState(err.message);
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
