/* Hash routing.
 *
 * Hash rather than the History API, for one practical reason: FastAPI serves this as a
 * static file at a single path. Real paths would need every route to fall back to
 * index.html on the server, which is an extra piece of deployment configuration that can
 * be got wrong — and deployment is the risk this project has worked hardest to remove.
 *
 * Routes declare the roles allowed to reach them. A route someone may not use is not
 * merely refused, it is absent from their navigation — showing a control and then
 * rejecting it teaches people the interface lies.
 */

const routes = new Map();
let notFound = () => "<div class='empty'><strong>Not found</strong>That page does not exist.</div>";
let current = null;
let getRole = () => null;

export function define(path, { render, roles = null, title = "Nkwanta" }) {
  routes.set(path, { render, roles, title });
}

export function setRoleProvider(fn) { getRole = fn; }
export function setNotFound(fn) { notFound = fn; }

export function allowed(path, role) {
  const route = routes.get(path);
  if (!route) return false;
  if (!route.roles) return true;               // open to everyone, signed in or not
  return role !== null && route.roles.includes(role);
}

export const currentPath = () => (location.hash.slice(1) || "/").split("?")[0];

export function go(path, { replace = false } = {}) {
  if (replace) location.replace(`#${path}`);
  else location.hash = path;
}

export function query() {
  const raw = (location.hash.split("?")[1] || "");
  return Object.fromEntries(new URLSearchParams(raw));
}

/** Render the current route into `mount`. Returns the route so callers can react. */
export async function resolve(mount) {
  const path = currentPath();
  const route = routes.get(path);
  const role = getRole();

  if (!route) {
    mount.innerHTML = notFound();
    return null;
  }

  if (route.roles && !allowed(path, role)) {
    // Send them somewhere they can actually be rather than showing a wall.
    go(role ? "/" : "/signin", { replace: true });
    return null;
  }

  // Tear down whatever was there — views may hold map instances, timers or recorders.
  current?.destroy?.();
  document.title = route.title;

  mount.innerHTML = "";
  current = (await route.render(mount)) || null;
  mount.scrollTop = 0;
  return route;
}

export function start(mount, onNavigate) {
  const run = async () => {
    const route = await resolve(mount);
    onNavigate?.(currentPath(), route);
  };
  window.addEventListener("hashchange", run);
  if (!location.hash) go("/", { replace: true });
  return run;
}
