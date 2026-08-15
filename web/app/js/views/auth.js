/* Sign in and register.
 *
 * The registration form has no role field, and that is not an oversight — it mirrors the
 * API, where `RegisterRequest` has no role field either. Self-registration always
 * produces a commuter. Wardens, officers and admins are created by an admin.
 */

import { api, auth } from "../api.js";
import { go } from "../router.js";
import { loadUser, refreshAll } from "../store.js";
import { esc, icon, rules, toast, validate } from "../ui.js";

/* `start` lets a caller land on the register tab directly — the "Create an account"
 * button on the signed-out map means it, and making somebody arrive on the sign-in form
 * and then find the right tab is a step that exists for no reason. */
export default function authView(mount, { start = "login" } = {}) {
  let mode = start;

  mount.innerHTML = `
    <div class="scroll pad">
      <div class="card" style="max-width:420px;margin:0 auto">
        <div class="inline" style="gap:6px;margin-bottom:16px" role="tablist">
          <button class="btn btn--ghost btn--sm" data-mode="login" role="tab" aria-selected="true">Sign in</button>
          <button class="btn btn--ghost btn--sm" data-mode="register" role="tab" aria-selected="false">Create account</button>
        </div>

        <form id="f" novalidate>
          <div class="field hide" id="nameField">
            <label for="display_name">Your name <span class="req">*</span></label>
            <input class="input" id="display_name" name="display_name" autocomplete="name" placeholder="Ama Owusu">
            <div class="err" data-err="display_name"></div>
          </div>

          <div class="field" style="margin-top:12px">
            <label for="email">Email <span class="req">*</span></label>
            <input class="input" id="email" name="email" type="email" autocomplete="username"
                   inputmode="email" placeholder="commuter@nkwanta.demo">
            <div class="err" data-err="email"></div>
          </div>

          <div class="field" style="margin-top:12px">
            <label for="password">Password <span class="req">*</span></label>
            <input class="input" id="password" name="password" type="password"
                   autocomplete="current-password" placeholder="At least 8 characters">
            <div class="err" data-err="password"></div>
          </div>

          <button class="btn btn--block" id="submit" style="margin-top:18px" disabled>Sign in</button>
        </form>

        // <p class="hint" style="margin-top:16px;line-height:1.6">
        //   Demonstration accounts, password <code>NkwantaDemo2026</code>:<br>
        //   <code>commuter@</code>, <code>warden@</code>, <code>officer@</code>, <code>admin@nkwanta.demo</code>
        // </p>
        <p class="hint" id="roleNote" style="display:none">
          New accounts are always commuters. Warden and officer accounts are created by an
          administrator — nobody registers themselves as police.
        </p>
      </div>
    </div>`;

  const form = mount.querySelector("#f");
  const submit = mount.querySelector("#submit");
  const nameField = mount.querySelector("#nameField");

  let v = wire();

  function wire() {
    const r = { email: rules.email(), password: rules.password() };
    if (mode === "register") r.display_name = rules.minLength(2, "Your name");
    return validate(form, r, submit);
  }

  mount.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      mode = btn.dataset.mode;
      mount.querySelectorAll("[data-mode]").forEach(b =>
        b.setAttribute("aria-selected", String(b === btn)));
      nameField.classList.toggle("hide", mode === "login");
      mount.querySelector("#roleNote").style.display = mode === "register" ? "block" : "none";
      submit.textContent = mode === "login" ? "Sign in" : "Create account";
      mount.querySelector("#password").autocomplete =
        mode === "login" ? "current-password" : "new-password";
      v = wire();
    });
  });

  // After the listeners exist, not before — the tab is switched by firing the same
  // handler a tap would, so there is one code path for entering register mode rather
  // than a second that has to be kept in step with it.
  if (mode === "register") mount.querySelector('[data-mode="register"]').click();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!v.validateAll()) return;

    const body = {
      email: form.email.value.trim().toLowerCase(),
      password: form.password.value,
    };
    if (mode === "register") body.display_name = form.display_name.value.trim();

    submit.disabled = true;
    submit.textContent = mode === "login" ? "Signing in…" : "Creating…";
    try {
      const res = await api(`/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
      auth.token = res.access_token;
      await loadUser();
      refreshAll();
      toast(mode === "login" ? "Signed in" : "Welcome to Nkwanta");
      go("/");
    } catch (err) {
      toast(err.message, { error: true });
      submit.disabled = false;
      submit.textContent = mode === "login" ? "Sign in" : "Create account";
    }
  });

  return { destroy() {} };
}
