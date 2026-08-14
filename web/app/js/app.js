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

  // Signed out, the only navigation offered is the map and a way in. A tab bar of
  // things that would bounce you to a sign-in page is worse than no tab bar.
  if (!auth.signedIn) {
    tabs.innerHTML = `
      <a href="#/" ${current === "/" ? 'aria-current="page"' : ""}>${icon("map",20)}<span>Map</span></a>
      <a href="#/signin" class="fab">${icon("user",20)}<span>Sign in</span></a>`;
  }
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

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/app/sw.js", { scope: "/static/app/" })
      .catch(() => {/* the app works without it, just not offline */});
  }
}

main();
