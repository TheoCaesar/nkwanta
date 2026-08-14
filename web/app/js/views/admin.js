/* Administration: accounts, system state, and the demonstration controls.
 *
 * This is the interface for a capability that existed in the API from B03 and was
 * invisible until now — POST /auth/users is the only way a warden or officer account
 * comes into being, other than the seed script.
 *
 * The gateway controls exist for the demonstration and are recorded as debt TD-21. They
 * are labelled as such here rather than presented as a feature.
 */

import { api } from "../api.js";
import { esc, icon, closeSheet, empty, errorState, pct, rules, sheet, skeleton, toast, validate, avatar } from "../ui.js";

const ROLES = ["commuter", "warden", "officer", "admin"];

export default function adminView(mount) {
  let users = [];
  let filter = "all";

  mount.innerHTML = `
    <div class="scroll pad stack">
      <div class="card">
        <h2>System</h2>
        <div class="inline" style="gap:22px" id="stats">${skeleton(1)}</div>
      </div>

      <div class="card">
        <div class="row-between">
          <h2 style="margin:0">Accounts</h2>
          <button class="btn btn--sm" id="new">${icon("plus",14)} New account</button>
        </div>
        <p class="hint" style="margin:6px 0 12px">
          Wardens and officers can only be created here. Self-registration always produces a
          commuter — the request has no role field at all.
        </p>
        <div class="chips" id="filters" style="margin-bottom:12px">
          ${["all", ...ROLES].map(r =>
            `<button class="chip" data-filter="${esc(r)}" aria-pressed="${r === "all"}">${esc(r === "all" ? "All" : r)}</button>`
          ).join("")}
        </div>
        <div class="list" id="users">${skeleton(4)}</div>
      </div>

      <div class="card">
        <h2>Notification gateway</h2>
        <div id="gateway">${skeleton(2)}</div>
        <p class="hint" style="margin-top:10px">
          The circuit breaker stops the system calling a provider that is clearly down —
          five consecutive failures and it refuses instantly instead of waiting thirty
          seconds each time. Breaking the gateway on purpose is a demonstration control and
          should not exist in a real deployment (TD-21).
        </p>
        <div class="inline" style="margin-top:12px">
          <button class="btn btn--ghost btn--sm" id="fail">Break the gateway</button>
          <button class="btn btn--ghost btn--sm" id="heal">Restore it</button>
          <button class="btn btn--ghost btn--sm" id="reset">Force breaker closed</button>
        </div>
      </div>

      <div class="card">
        <h2>Demonstration data</h2>
        <p class="hint" style="margin-bottom:12px">
          Accuracy halves every 45 minutes, so seeded data fades. Refresh it shortly before
          a demonstration or the map will look empty.
        </p>
        <div class="inline">
          <button class="btn btn--ghost btn--sm" id="seed">Refresh demo data</button>
          <button class="btn btn--ghost btn--sm" id="drain">Process outbox now</button>
          <button class="btn btn--ghost btn--sm" id="sweep">Fade stale incidents</button>
        </div>
      </div>
    </div>`;

  load();

  mount.querySelector("#new").addEventListener("click", createAccount);
  mount.querySelectorAll("[data-filter]").forEach(b =>
    b.addEventListener("click", () => {
      filter = b.dataset.filter;
      mount.querySelectorAll("[data-filter]").forEach(x =>
        x.setAttribute("aria-pressed", String(x === b)));
      renderUsers();
    }));

  bind("#fail", "/admin/gateway/fail", "Gateway will now refuse every send");
  bind("#heal", "/admin/gateway/heal", "Gateway restored — the breaker waits before testing it");
  bind("#reset", "/admin/gateway/reset", "Breaker forced closed");
  bind("#seed", "/admin/seed", "Demonstration data refreshed");
  bind("#drain", "/admin/drain", "Outbox processed");
  bind("#sweep", "/admin/sweep", "Stale incidents faded");

  function bind(selector, path, message) {
    mount.querySelector(selector).addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api(path, { method: "POST" });
        toast(message);
        load();
      } catch (err) { toast(err.message, { error: true }); }
      finally { btn.disabled = false; }
    });
  }

  async function load() {
    const [stats, gateway, list] = await Promise.allSettled([
      api("/admin/stats"), api("/admin/gateway"), api("/auth/users?limit=200"),
    ]);

    if (stats.status === "fulfilled") renderStats(stats.value);
    if (gateway.status === "fulfilled") renderGateway(gateway.value);
    if (list.status === "fulfilled") { users = list.value; renderUsers(); }
    else mount.querySelector("#users").innerHTML = errorState(list.reason?.message ?? "Could not load accounts");
  }

  function renderStats(s) {
    mount.querySelector("#stats").innerHTML = [
      [s.users, "accounts"], [s.reports, "reports"], [s.incidents, "incidents"],
      [s.incidents_verified, "verified"], [s.notifications, "alerts sent"],
      [s.outbox_pending, "queued"],
    ].map(([n, label]) =>
      `<span><strong style="font-size:20px">${n}</strong>
       <span class="xs" style="display:block">${esc(label)}</span></span>`).join("");
  }

  function renderGateway(g) {
    const b = g.breaker;
    const tone = { closed: "resolved", half_open: "corroborated", open: "verified" }[b.state] ?? "reported";
    mount.querySelector("#gateway").innerHTML = `
      <div class="row-between">
        <span class="grow">
          <span class="t">Circuit breaker</span>
          <span class="m">${b.total_successes} sent · ${b.total_failures} failed
            · ${b.total_rejected_without_trying} refused without trying
            · opened ${b.times_opened}×</span>
        </span>
        <span class="tag tag--${tone}">${esc(b.state.replace("_"," "))}</span>
      </div>
      ${b.retry_at ? `<div class="hint" style="margin-top:8px">Will test the gateway again at
        ${esc(new Date(b.retry_at).toLocaleTimeString("en-GB"))}.</div>` : ""}
      <div class="hint" style="margin-top:6px">Provider is
        ${g.gateway_healthy ? "healthy" : "<strong>deliberately broken</strong>"}.</div>`;
  }

  function renderUsers() {
    const box = mount.querySelector("#users");
    const shown = filter === "all" ? users : users.filter(u => u.role === filter);
    if (!shown.length) { box.innerHTML = empty("No accounts", "Nothing matches that filter."); return; }

    box.innerHTML = shown.map(u => `
      <div class="row-between">
        <span class="inline grow">
          ${avatar(u.display_name, u.id, 32)}
          <span class="grow">
            <span class="t">${esc(u.display_name)}</span>
            <span class="m">${esc(u.email)}</span>
          </span>
        </span>
        <span style="text-align:right">
          <span class="tag tag--${u.role === "officer" ? "assigned" : "reported"}">${esc(u.role)}</span>
          <span class="m num">${pct(u.reputation)}
            ${u.reports_confirmed || u.reports_contradicted
              ? `· ${u.reports_confirmed}✓ ${u.reports_contradicted}✗` : ""}</span>
        </span>
      </div>`).join("");
  }

  function createAccount() {
    sheet({
      title: "New account",
      body: `
        <form id="af" novalidate>
          <div class="field">
            <label for="an">Name <span class="req">*</span></label>
            <input class="input" id="an" name="display_name" maxlength="80" placeholder="Kwesi Boateng">
            <div class="err" data-err="display_name"></div>
          </div>
          <div class="field" style="margin-top:14px">
            <label for="ae">Email <span class="req">*</span></label>
            <input class="input" id="ae" name="email" type="email" inputmode="email" placeholder="warden2@nkwanta.demo">
            <div class="err" data-err="email"></div>
          </div>
          <div class="field" style="margin-top:14px">
            <label for="ap">Password <span class="req">*</span></label>
            <input class="input" id="ap" name="password" type="password" autocomplete="new-password">
            <div class="hint">At least 8 characters. Tell them to change it.</div>
            <div class="err" data-err="password"></div>
          </div>
          <div class="field" style="margin-top:14px">
            <label for="ar">Role <span class="req">*</span></label>
            <select class="input" id="ar" name="role">
              ${ROLES.map(r => `<option style="text-transform:capitalize" value="${esc(r)}">${esc(r)}</option>`).join("")}
            </select>
            <div class="hint">A warden receives assignments. An officer runs the dispatch queue.</div>
          </div>
        </form>`,
      footer: `<button class="btn btn--block" id="mk" form="af">Create account</button>`,
      onMount: (el) => {
        const form = el.querySelector("#af");
        const btn = el.querySelector("#mk");
        const v = validate(form, {
          display_name: rules.minLength(2, "A name"),
          email: rules.email(),
          password: rules.password(),
        }, btn);

        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          if (!v.validateAll()) return;
          btn.disabled = true; btn.textContent = "Creating…";
          try {
            await api("/auth/users", {
              method: "POST",
              body: JSON.stringify({
                display_name: form.display_name.value.trim(),
                email: form.email.value.trim().toLowerCase(),
                password: form.password.value,
                role: form.role.value,
              }),
            });
            closeSheet();
            toast("Account created");
            load();
          } catch (err) {
            toast(err.message, { error: true });
            btn.disabled = false; btn.textContent = "Create account";
          }
        });
      },
    });
  }

  return { destroy() { closeSheet(); } };
}
