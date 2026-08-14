/* Service worker.
 *
 * Two jobs, and a lot of restraint about not doing a third.
 *
 *   1. Cache the shell, so the application opens with no connection.
 *   2. Cache the last incident feed, so it opens with something to show.
 *
 * It deliberately does NOT try to replay queued reports through Background Sync. That
 * API is unavailable on iOS and unreliable elsewhere, and a queue that works on some
 * phones is worse than one that works predictably on all of them. Sending is handled in
 * the page, on the `online` event and at startup — see js/api.js.
 *
 * Nothing that mutates data is ever cached. A cached POST would mean a report appearing
 * to succeed twice, or an assignment silently replaying.
 */

/* Bump this on every deploy that changes a shell file.
 *
 * It is the only thing that evicts the old cache, and forgetting it is the classic
 * service-worker failure: the fix is deployed, the server is serving it, and the user is
 * still running last week's JavaScript because `cacheFirst` handed them the copy it
 * already had. `cacheFirst` does revalidate behind the response, so the new file arrives
 * — but only on the load *after* the one where it was needed, which is indistinguishable
 * from the fix not working.
 *
 * It sat at v1 through the whole build, which is a deployment bug, not a caching policy.
 */
const VERSION = "v4-2026-08-14-root";
const SHELL = `nkwanta-shell-${VERSION}`;
const DATA = `nkwanta-data-${VERSION}`;

const SHELL_FILES = [
  // The document itself, at the address the manifest starts from. This used to be
  // "/static/app/", which was never a route — `cache.add` failed on it silently every
  // install, and `Promise.allSettled` below is why nobody noticed.
  "/",
  "/static/app/index.html",
  "/static/app/css/app.css",
  "/static/app/js/app.js",
  "/static/app/js/api.js",
  "/static/app/js/router.js",
  "/static/app/js/store.js",
  "/static/app/js/ui.js",
  "/static/app/js/views/map.js",
  "/static/app/js/views/report.js",
  "/static/app/js/views/alerts.js",
  "/static/app/js/views/routes.js",
  "/static/app/js/views/profile.js",
  "/static/app/js/views/auth.js",
  "/static/app/js/views/dispatch.js",
  "/static/app/js/views/admin.js",
  "/static/app/manifest.webmanifest",
  "/static/app/icons/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) =>
      // addAll fails the whole install if any one file 404s, which would leave the app
      // with no shell at all. Add individually and tolerate a miss.
      Promise.allSettled(SHELL_FILES.map((f) => cache.add(f)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only GET is ever cached or served from cache. Anything that changes state must
  // reach the server or fail honestly.
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;      // map tiles, CDN: leave alone

  // Never cache anything that identifies a person or could go stale dangerously.
  if (url.pathname.startsWith("/attachments/") || url.pathname.startsWith("/auth/")) return;

  // The incident LIST only. Never a single incident.
  //
  // A detail response contains the evidence its viewer was entitled to see — a private
  // recording, and a live signed URL for it — and the cache is keyed by URL alone, with
  // no notion of who asked. Caching one would mean the reporter views their own incident,
  // signs out, and the next person on that phone is served their recording from the cache
  // along with a token that still works.
  //
  // The list is identical for everybody, so it is safe to keep and is the thing worth
  // having offline anyway: which roads are blocked.
  if (url.pathname === "/incidents" || url.pathname.startsWith("/incidents?")) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (url.pathname.startsWith("/static/app/")) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // The document itself. Now that the worker has root scope it controls the page, which
  // is the whole point of installing it — served from cache so the app opens with no
  // connection, and revalidated behind the response so a deploy still lands.
  //
  // One entry is enough: routing is by hash, so every address in the application is the
  // same document and hash changes never reach the network.
  if (request.mode === "navigate") {
    event.respondWith(cacheFirst(new Request("/", { credentials: "same-origin" })));
  }
});

/** Fresh data when possible; the last copy when not. */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(DATA);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) {
      // Tell the page this is stale so it can say so rather than pretending.
      const headers = new Headers(cached.headers);
      headers.set("X-Nkwanta-Cached", "1");
      return new Response(await cached.blob(), {
        status: cached.status, statusText: cached.statusText, headers,
      });
    }
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json", "X-Nkwanta-Cached": "empty" },
    });
  }
}

/** Shell files change only on deploy, so serve them instantly and refresh behind. */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    fetch(request).then((res) => {
      if (res.ok) caches.open(SHELL).then((c) => c.put(request, res));
    }).catch(() => {});
    return cached;
  }
  try {
    const res = await fetch(request);
    if (res.ok) (await caches.open(SHELL)).put(request, res.clone());
    return res;
  } catch {
    return (await caches.match("/")) ?? (await caches.match("/static/app/index.html"));
  }
}
