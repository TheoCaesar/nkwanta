/* Application state.
 *
 * Small enough not to need a state library: a plain object, a set of subscribers, and a
 * notify call. Roughly forty lines doing the job a framework would charge a build step
 * for — see decision D-037.
 */

import { api, auth, outbox } from "./api.js";

const listeners = new Set();

export const state = {
  user: null,
  incidents: [],
  notifications: [],
  unread: 0,
  corridors: [],
  queued: 0,
  online: navigator.onLine,
  loading: false,
  error: null,
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function set(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn(state);
}

export const role = () => state.user?.role ?? null;
export const isStaff = () => ["officer", "admin"].includes(role());

/* ------------------------------------------------------------------ sessions */

export async function loadUser() {
  if (!auth.signedIn) { set({ user: null }); return null; }
  try {
    const user = await api("/auth/me");
    set({ user });
    return user;
  } catch {
    // A token that no longer works is the same as no token. Do not strand the user on
    // a broken session — sign them out and let them sign in again.
    auth.token = null;
    set({ user: null });
    return null;
  }
}

export function signOut() {
  auth.token = null;
  set({ user: null, notifications: [], unread: 0, corridors: [] });
}

/* -------------------------------------------------------------------- refresh */

export async function refreshIncidents() {
  const incidents = await api("/incidents?limit=200");
  set({ incidents });
  return incidents;
}

export async function refreshNotifications() {
  if (!auth.signedIn) return;
  const [notifications, count] = await Promise.all([
    api("/notifications?limit=50"),
    api("/notifications/count"),
  ]);
  set({ notifications, unread: count.unread });
}

export async function refreshCorridors() {
  if (!auth.signedIn) return;
  set({ corridors: await api("/corridors") });
}

export async function refreshQueue() {
  set({ queued: await outbox.count() });
}

/** Everything the shell needs, in parallel, tolerating individual failures.
 *  One endpoint being down should not blank the whole interface. */
export async function refreshAll() {
  await Promise.allSettled([
    refreshIncidents(),
    refreshNotifications(),
    refreshCorridors(),
    refreshQueue(),
  ]);
}
