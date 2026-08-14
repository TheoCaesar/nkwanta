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

const VERSION = "v1";
const SHELL = `nkwanta-shell-${VERSION}`;
const DATA = `nkwanta-data-${VERSION}`;

const SHELL_FILES = [
  "/static/app/",
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

  if (url.pathname.startsWith("/incidents")) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (url.pathname.startsWith("/static/app/")) {
    event.respondWith(cacheFirst(request));
    return;
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
    return caches.match("/static/app/index.html");
  }
}
