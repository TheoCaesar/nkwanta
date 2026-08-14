/* Bootstrap: register the routes, draw the shell, keep it in step with state.
 *
 * The shell is the appbar, the banners and the navigation. Views own everything inside
 * #view and nothing outside it.
 */

import { auth, connection, flushOutbox, outbox } from "./api.js";
import * as router from "./router.js";
import { loadUser, refreshAll, refreshQueue, role, set, state, subscribe } from "./store.js";
import { esc, icon, toast } from "./ui.js";

import mapView from "./views/map.js";
import reportView from "./views/report.js";
import alertsView from "./views/alerts.js";
import routesView from "./views/routes.js";
import profileView from "./views/profile.js";
import authView from "./views/auth.js";
import dispatchView from "./views/dispatch.js";
import adminView from "./views/admin.js";

const view = document.getElementById("view");
const tabs = document.getElementById("tabs");
const banners = document.getElementById("banners");
const title = document.getElementById("title");
const actions = document.getElementById("appbar-actions");

/* ------------------------------------------------------------------- routes */

router.setRoleProvider(role);

router.define("/",         { render: mapView,      title: "Nkwanta — map" });
router.define("/signin",   { render: authView,     title: "Nkwanta — sign in" });
router.define("/register", { render: (m) => authView(m, { start: "register" }),
                             title: "Nkwanta — create account" });
router.define("/report",   { render: reportView,   title: "Nkwanta — report", roles: ["commuter","warden","officer","admin"] });
router.define("/alerts",   { render: alertsView,   title: "Nkwanta — alerts", roles: ["commuter","warden","officer","admin"] });
router.define("/routes",   { render: routesView,   title: "Nkwanta — routes", roles: ["commuter","warden","officer","admin"] });
router.define("/you",      { render: profileView,  title: "Nkwanta — profile", roles: ["commuter","warden","officer","admin"] });
router.define("/dispatch", { render: dispatchView, title: "Nkwanta — dispatch", roles: ["warden","officer","admin"] });
router.define("/admin",    { render: adminView,    title: "Nkwanta — administration", roles: ["admin"] });

/* --------------------------------------------------------------- navigation */

const TABS = [
  { path: "/",         label: "Map",      icon: "map" },
  { path: "/alerts",   label: "Alerts",   icon: "bell",     badge: () => state.unread },
  { path: "/report",   label: "Report",   icon: "plus",     fab: true },
  { path: "/routes",   label: "Routes",   icon: "route" },
  { path: "/you",      label: "You",      icon: "user" },
  { path: "/dispatch", label: "Dispatch", icon: "urgent" },
  { path: "/admin",    label: "Admin",    icon: "settings" },
];

function drawTabs() {
  const current = router.currentPath();

  /* Signed out, there is no navigation at all — D-044.
   *
   * It previously showed two tabs, Map and Sign in, which is a navigation bar whose
   * every item is either where you already are or the thing the appbar button already
   * does. Before that it showed five, four of which would bounce you to a sign-in page.
   *
   * A console with every item greyed out advertises a product the visitor cannot use.
   * Removing it makes the map the page, which is what the map should have been: the
   * front door, with one control on it.
   *
   * `signedOut` on the shell is what collapses the bar, rather than emptying it — an
   * empty <nav> still holds its height and its border, leaving a stripe of nothing
   * along the bottom of the screen. */
  document.getElementById("app").classList.toggle("signedOut", !auth.signedIn);
  if (!auth.signedIn) { tabs.innerHTML = ""; return; }

  const r = role();
  tabs.innerHTML = TABS
    .filter(t => router.allowed(t.path, r))
    .map(t => {
      const count = t.badge?.() || 0;
      return `<a href="#${t.path}" class="${t.fab ? "fab" : ""}"
                 ${current === t.path ? 'aria-current="page"' : ""}>
                ${icon(t.icon, 20)}<span>${esc(t.label)}</span>
                ${count ? `<span class="badge">${count > 9 ? "9+" : count}</span>` : ""}
              </a>`;
    }).join("");
}

function drawActions() {
  actions.innerHTML = auth.signedIn
    ? `<a href="#/you" class="btn btn--ghost btn--sm">${esc(state.user?.display_name ?? "You")}</a>`
    : `<a href="#/signin" class="btn btn--sm">Sign in</a>`;
}

function drawBanners() {
  const parts = [];
  if (!state.online) {
    parts.push(`<div class="banner banner--offline">${icon("wifi_off",16)}
      <span>No connection — showing what was last loaded</span></div>`);
  }
  if (state.queued) {
    parts.push(`<div class="banner banner--queued">${icon("urgent",16)}
      <span>${state.queued} report${state.queued === 1 ? "" : "s"} waiting to send.
      ${state.online ? "Sending now…" : "They will send when you have signal."}</span></div>`);
  }
  banners.innerHTML = parts.join("");
}

function drawShell() {
  drawTabs(); drawActions(); drawBanners();
}

/* -------------------------------------------------------------------- start */

async function main() {
  subscribe(drawShell);

  connection.watch((online) => {
    set({ online });
    if (online) toast("Back online");
  })();

  window.addEventListener("nk:queuechanged", refreshQueue);
  window.addEventListener("nk:queuerejected", (e) => {
    toast(`A queued report was rejected: ${e.detail.message}`, { error: true });
  });
  window.addEventListener("nk:signedout", () => {
    set({ user: null });
    toast("Your session expired. Sign in again.", { error: true });
    router.go("/signin");
  });

  await loadUser();
  drawShell();

  const run = router.start(view, (path) => {
    drawTabs();
    const label = TABS.find(t => t.path === path)?.label;
    title.textContent = label && path !== "/" ? `Nkwanta — ${label.toLowerCase()}` : "Nkwanta";
  });
  await run();

  // Anything queued from a previous visit goes now, before the user does anything.
  flushOutbox().then(({ sent }) => {
    if (sent) toast(`${sent} queued report${sent === 1 ? "" : "s"} sent`);
    refreshQueue();
  });

  refreshAll();
  setInterval(() => { if (state.online) refreshAll(); }, 30000);

  installServiceWorker();
}

/* The service worker is a production feature, and on a development machine it is an
 * obstacle.
 *
 * `cacheFirst` hands back the copy it already has, so an edit to a module does not appear
 * until the load *after* the one where it was made. That is correct behaviour for a
 * commuter on a bad connection and useless behaviour for anyone editing the file: the
 * server is serving the new code, the page is running the old code, and the two look
 * identical from the outside. It cost an hour before it was recognised.
 *
 * So it does not register on localhost — and, because a worker already registered keeps
 * controlling the page whatever we do next, it actively unregisters any it finds and
 * empties the caches. Skipping registration alone would have left every machine that has
 * already run this app still stale.
 *
 * Offline report queuing is unaffected: that lives in IndexedDB, in api.js, and has never
 * depended on the worker. What is lost locally is offline *shell* caching, which is
 * tested against the deployed site where it actually matters.
 */
const DEVELOPMENT_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", ""]);

async function installServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  if (DEVELOPMENT_HOSTS.has(location.hostname)) {
    const registrations = await navigator.serviceWorker.getRegistrations().catch(() => []);
    await Promise.all(registrations.map(r => r.unregister()));
    if (window.caches) {
      const keys = await caches.keys().catch(() => []);
      await Promise.all(keys.map(k => caches.delete(k)));
    }
    if (registrations.length) {
      // The page currently rendered was served by the worker that has just been removed,
      // so it is still the stale one. Say so rather than leave the developer looking at
      // code they have already changed.
      console.info("Nkwanta: service worker removed for local development. Reload once.");
    }
    return;
  }

  navigator.serviceWorker.register("/static/app/sw.js", { scope: "/static/app/" })
    .catch(() => {/* the app works without it, just not offline */});
}

main();
