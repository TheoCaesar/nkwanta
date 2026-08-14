/* The API layer, and the offline queue.
 *
 * Everything the interface knows about the server goes through here. Two jobs:
 * authenticated fetch, and surviving a bad connection.
 *
 *
 * WHY AN OFFLINE QUEUE
 * --------------------
 * NFR-2 says the system must work on 3G and low-end Android. The user this exists for is
 * standing at a flooded junction with one bar of signal — and that is exactly when a
 * report matters most and is least likely to send.
 *
 * So a report filed with no connection is written to IndexedDB and sent when the
 * connection returns. The user is told it is queued rather than told it failed.
 *
 * This is only safe because of a decision made at B04, long before there was a client:
 * every report carries an idempotency key generated at capture. A queued report retried
 * three times still creates one report, so a flaky connection cannot inflate an
 * incident's confidence.
 */

const TOKEN_KEY = "nk.token";
const DB_NAME = "nkwanta";
const DB_VERSION = 1;
const STORE = "outbox";

/* ---------------------------------------------------------------- auth state */

export const auth = {
  get token() {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  set token(value) {
    // sessionStorage rather than localStorage: it dies with the tab, so a shared phone
    // does not stay signed in. Neither is ideal — a httpOnly cookie is the right answer
    // and needs CSRF protection with it. Recorded as debt.
    if (value) sessionStorage.setItem(TOKEN_KEY, value);
    else sessionStorage.removeItem(TOKEN_KEY);
  },
  get signedIn() {
    return Boolean(this.token);
  },
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class OfflineError extends Error {
  constructor() {
    super("No connection");
    this.name = "OfflineError";
  }
}

/* ------------------------------------------------------------------ requests */

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let res;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    // fetch only rejects on a network failure, never on an HTTP error status.
    throw new OfflineError();
  }

  if (res.status === 401 && auth.token) {
    auth.token = null;
    window.dispatchEvent(new CustomEvent("nk:signedout"));
  }

  if (res.status === 204) return null;

  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    throw new ApiError(errorMessage(data, res), res.status);
  }
  return data;
}

function safeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

function errorMessage(data, res) {
  if (!data) return `Request failed (${res.status})`;
  if (typeof data.detail === "string") return data.detail;
  // FastAPI validation errors arrive as a list. Surface the first in plain words rather
  // than showing someone a JSON dump.
  if (Array.isArray(data.detail) && data.detail.length) {
    const first = data.detail[0];
    const field = (first.loc || []).filter(p => p !== "body").join(" ");
    return field ? `${field}: ${first.msg}` : first.msg;
  }
  return `Request failed (${res.status})`;
}

/* -------------------------------------------------------------- the outbox db */

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function withStore(mode, fn) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const result = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(result?.result ?? result);
    tx.onerror = () => reject(tx.error);
  });
}

export const outbox = {
  async add(entry) {
    await withStore("readwrite", store => store.put(entry));
    window.dispatchEvent(new CustomEvent("nk:queuechanged"));
  },
  async all() {
    const rows = await withStore("readonly", store => store.getAll());
    return (rows || []).sort((a, b) => a.queuedAt - b.queuedAt);
  },
  async remove(id) {
    await withStore("readwrite", store => store.delete(id));
    window.dispatchEvent(new CustomEvent("nk:queuechanged"));
  },
  async count() {
    return (await this.all()).length;
  },
};

/* ------------------------------------------------------------ report sending */

/** Submit a report, or queue it if there is no connection.
 *
 *  Returns { queued: true } when it could not be sent. The caller tells the user it is
 *  waiting rather than that it failed — because it has not failed, it is pending.
 */
export async function submitReport({ body, photo, voice, shareVoice }) {
  // The idempotency key is generated HERE, at capture, not at send. That is what makes
  // a retry safe: the same physical report carries the same key however many times it
  // is attempted. See app/services/reports.py.
  const payload = { ...body, idempotency_key: body.idempotency_key || crypto.randomUUID() };

  const entry = {
    id: payload.idempotency_key,
    queuedAt: Date.now(),
    payload,
    photo: photo || null,
    voice: voice || null,
    shareVoice: Boolean(shareVoice),
  };

  if (!navigator.onLine) {
    await outbox.add(entry);
    return { queued: true, entry };
  }

  try {
    return { queued: false, ...(await sendEntry(entry)) };
  } catch (err) {
    if (err instanceof OfflineError) {
      await outbox.add(entry);
      return { queued: true, entry };
    }
    throw err;
  }
}

async function sendEntry(entry) {
  const result = await api("/reports", {
    method: "POST",
    body: JSON.stringify(entry.payload),
  });

  const reportId = result.report.id;

  // Attachments follow the report, because they need its id. A failure here leaves the
  // report standing — evidence is an addition to a report, never a precondition for one.
  //
  // But it is reported rather than swallowed. These calls used to end in `.catch(() => {})`,
  // which meant a rejected photograph or recording vanished without a word: the user saw
  // "Reported. Thank you.", and their evidence was simply not there. Silence about a
  // failure the user could act on — a file too large, a format the server will not take —
  // is worse than the failure.
  const rejected = [];

  if (entry.photo) {
    const fd = new FormData();
    fd.append("file", entry.photo, entry.photo.name || "photo.jpg");
    try {
      await api(`/reports/${reportId}/photo`, { method: "POST", body: fd });
    } catch (err) {
      rejected.push(`photograph (${err.message})`);
    }
  }

  if (entry.voice) {
    const fd = new FormData();
    fd.append("file", entry.voice, "voice.webm");
    fd.append("share_publicly", String(entry.shareVoice));
    try {
      await api(`/reports/${reportId}/voice`, { method: "POST", body: fd });
    } catch (err) {
      rejected.push(`recording (${err.message})`);
    }
  }

  return { ...result, rejected };
}

/** Drain the queue oldest first. Anything that fails stays queued for next time. */
export async function flushOutbox() {
  if (!navigator.onLine) return { sent: 0, remaining: await outbox.count() };

  let sent = 0;
  for (const entry of await outbox.all()) {
    try {
      await sendEntry(entry);
      await outbox.remove(entry.id);
      sent += 1;
    } catch (err) {
      if (err instanceof OfflineError) break;   // connection went again; stop trying
      // A rejected report — bad coordinates, too old — would be retried forever
      // otherwise, blocking everything behind it. Drop it and tell the user.
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
        await outbox.remove(entry.id);
        window.dispatchEvent(new CustomEvent("nk:queuerejected", {
          detail: { entry, message: err.message },
        }));
      } else {
        break;
      }
    }
  }
  return { sent, remaining: await outbox.count() };
}

/* ------------------------------------------------------------- connectivity */

export const connection = {
  get online() { return navigator.onLine; },
  watch(onChange) {
    const fire = () => onChange(navigator.onLine);
    window.addEventListener("online", () => { flushOutbox(); fire(); });
    window.addEventListener("offline", fire);
    return fire;
  },
};
