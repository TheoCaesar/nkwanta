/* Shared interface pieces: escaping, formatting, sheets, toasts, validation, states.
 *
 * The escaping helper is the important one. Display names, notes and messages all come
 * from users and are written into the DOM. Without escaping, a display name containing a
 * script tag executes — which in a system where an officer reads reporter names is a
 * direct path from "anyone can register" to "anyone can run code in the control room".
 */

/* ------------------------------------------------------------------ escaping */

const ENTITIES = { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" };

export const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ENTITIES[c]);

/** Tagged template that escapes every interpolation.
 *  Usage: html`<div>${userName}</div>` — impossible to forget. */
export function html(strings, ...values) {
  return strings.reduce((out, s, i) => out + s + (i < values.length ? esc(values[i]) : ""), "");
}

/** For the rare case where the value is already trusted markup we built ourselves. */
export const raw = (value) => ({ __raw: String(value) });

export function htmlRaw(strings, ...values) {
  return strings.reduce((out, s, i) => {
    if (i >= values.length) return out + s;
    const v = values[i];
    return out + s + (v && v.__raw !== undefined ? v.__raw : esc(v));
  }, "");
}

/* ---------------------------------------------------------------- formatting */

export function ago(iso) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

export const TYPE_LABEL = {
  accident: "Accident",
  flood: "Flooding",
  closure: "Road closure",
  signal_outage: "Traffic lights out",
  roadworks: "Roadworks",
  surface_defect: "Damaged road surface",
};

export const STATUS_COLOUR = {
  verified: "#C2453D",
  corroborated: "#D9A406",
  reported: "#8A968F",
  assigned: "#185FA5",
  resolved: "#0F6E56",
};

export const kb = (bytes) => `${Math.round(bytes / 1024)} KB`;

/** A 0–1 score as a whole percentage, ROUNDED DOWN.
 *
 *  Down rather than to nearest, deliberately. These numbers describe how much the system
 *  believes something, and rounding 0.899 up to 90% claims marginally more confidence
 *  than the arithmetic supports. Understating is the safe direction for a figure that
 *  decides whether police are called.
 */
export const pct = (value) => `${Math.floor((Number(value) || 0) * 100)}%`;

/* The interface says "accuracy" and "credibility" where the code and the API say
 * "confidence" and "reputation".
 *
 * The internal names are the correct technical ones and the documentation uses them.
 * But "confidence" invites a reader to hear certainty rather than corroboration, and
 * "reputation" sounds like a social score rather than a track record of reports that
 * turned out to be true. These two constants exist so the wording is decided in one
 * place rather than drifting across eight views.
 */
export const LABEL = {
  confidence: "Accuracy",
  reputation: "Credibility",
};

export function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/).slice(0, 2);
  return parts.map(p => p[0] ?? "").join("").toUpperCase() || "?";
}

/** Deterministic avatar colour from a user id.
 *  Same person, same colour, everywhere, with no stored preference and no PII —
 *  see decision D-038 on why there are no profile photographs. */
export function avatarColour(id) {
  const palette = ["#0F6E56", "#185FA5", "#7F4AA6", "#B4531F", "#1A7A6E", "#8A2F52"];
  let hash = 0;
  for (const ch of String(id)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

export function avatar(name, id, size = 36) {
  return `<span class="avatar" style="width:${size}px;height:${size}px;background:${avatarColour(id)};font-size:${Math.round(size / 2.7)}px" aria-hidden="true">${esc(initials(name))}</span>`;
}

/* --------------------------------------------------------------------- icons */

const ICONS = {
  map:'<path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 7 9 4Z"/><path d="M9 4v13M15 7v12.5"/>',
  bell:'<path d="M18 8a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7Z"/><path d="M10.3 20a2 2 0 0 0 3.4 0"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  route:'<circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/><path d="M15.5 5H9a3.5 3.5 0 0 0 0 7h6a3.5 3.5 0 0 1 0 7H8.5"/>',
  user:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5"/>',
  pin:'<path d="M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
  camera:'<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h2L8 5h8l1.5 2h2A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-9Z"/><circle cx="12" cy="13" r="3.5"/>',
  mic:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  search:'<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  x:'<path d="M6 6l12 12M18 6 6 18"/>',
  play:'<path d="M8 5.5v13l11-6.5-11-6.5Z"/>',
  check:'<path d="m5 13 4.5 4.5L19 7"/>',
  urgent:'<path d="M12 9v5M12 17.5v.5"/><path d="M10.3 4 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0Z"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 2.7-5 6-5s6 2 6 5"/><path d="M16 5.5a3 3 0 0 1 0 5.5M17 15c2.4.5 4 2.2 4 5"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15a2 2 0 0 1-2-2 2 2 0 0 1 2-2 1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 4.6 2 2 0 0 1 11 3a2 2 0 0 1 2 2 1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V13a2 2 0 0 1 0 4Z"/>',
  activity:'<path d="M3 12h4l3 8 4-16 3 8h4"/>',
  logout:'<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
  wifi_off:'<path d="M3 3l18 18"/><path d="M8.5 16.4a5 5 0 0 1 7 0M5 12.9a10 10 0 0 1 3-2M19 12.9a10 10 0 0 0-7-2.8"/><path d="M12 20h.01"/>',
};

export function icon(name, size = 20) {
  const body = ICONS[name] || "";
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

/* --------------------------------------------------------------------- states */

export const skeleton = (rows = 3) =>
  Array.from({ length: rows }, () => `
    <div style="padding:12px 0;border-bottom:1px solid var(--hair)">
      <div class="skel" style="width:55%"></div>
      <div class="skel" style="width:35%;margin-top:7px;height:10px"></div>
    </div>`).join("");

export const empty = (title, detail) => `
  <div class="empty"><strong>${esc(title)}</strong>${esc(detail || "")}</div>`;

export const errorState = (message, retryAction) => `
  <div class="empty">
    <strong>Something went wrong</strong>${esc(message)}
    ${retryAction ? `<div style="margin-top:12px"><button class="btn btn--ghost btn--sm" data-action="${esc(retryAction)}">Try again</button></div>` : ""}
  </div>`;

/* --------------------------------------------------------------------- toasts */

let toastEl = null;
let toastTimer = null;

const TOAST_ICON = { info: "activity", success: "check", warning: "urgent", error: "x" };

/** Show a message at the top of the screen.
 *
 *  `toast("Saved")`                        → info
 *  `toast("Reported", { type: "success" })`
 *  `toast(err.message, { error: true })`    → error, kept for existing callers
 *
 *  An error is announced assertively so a screen reader interrupts rather than waiting
 *  for a pause; everything else is polite. A failure the user is not told about promptly
 *  is a failure they act on.
 */
export function toast(message, { type, error = false, ms } = {}) {
  const kind = type || (error ? "error" : "info");

  if (!toastEl) {
    toastEl = document.createElement("div");
    document.body.appendChild(toastEl);
  }

  toastEl.className = `toast toast--${kind}`;
  toastEl.setAttribute("role", kind === "error" ? "alert" : "status");
  toastEl.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
  toastEl.innerHTML = `${icon(TOAST_ICON[kind] ?? "activity", 17)}<span>${esc(message)}</span>`;
  toastEl.setAttribute("data-open", "");

  clearTimeout(toastTimer);
  // Errors linger — they usually need reading twice, and often acting on.
  toastTimer = setTimeout(
    () => toastEl.removeAttribute("data-open"),
    ms ?? (kind === "error" ? 7000 : 4000),
  );
}

/* --------------------------------------------------------------------- sheets */

let openSheet = null;

/** Open a bottom sheet (side panel on desktop).
 *  Traps focus, closes on Escape and on scrim click, and restores focus afterwards —
 *  a modal that cannot be dismissed by keyboard is a trap. */
export function sheet({ title, body, footer, onMount, onClose }) {
  closeSheet();

  const previous = document.activeElement;
  const scrim = document.createElement("div");
  scrim.className = "scrim";

  const el = document.createElement("div");
  el.className = "sheet";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  el.setAttribute("aria-label", title);
  el.innerHTML = `
    <div class="sheet__grip"></div>
    <div class="sheet__head">
      <h2>${esc(title)}</h2>
      <button class="btn btn--ghost btn--sm" data-close aria-label="Close">${icon("x", 16)}</button>
    </div>
    <div class="sheet__body">${body}</div>
    ${footer ? `<div class="sheet__foot">${footer}</div>` : ""}`;

  document.body.append(scrim, el);
  requestAnimationFrame(() => {
    scrim.setAttribute("data-open", "");
    el.setAttribute("data-open", "");
  });

  const onKey = (e) => {
    if (e.key === "Escape") closeSheet();
    if (e.key !== "Tab") return;
    const focusable = el.querySelectorAll(
      'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  scrim.addEventListener("click", closeSheet);
  el.querySelector("[data-close]").addEventListener("click", closeSheet);
  document.addEventListener("keydown", onKey);

  openSheet = { el, scrim, onKey, previous, onClose };
  (el.querySelector("input,button:not([data-close])") || el).focus();
  onMount?.(el);
  return el;
}

export function closeSheet() {
  if (!openSheet) return;
  const { el, scrim, onKey, previous, onClose } = openSheet;
  openSheet = null;
  document.removeEventListener("keydown", onKey);
  el.removeAttribute("data-open");
  scrim.removeAttribute("data-open");
  setTimeout(() => { el.remove(); scrim.remove(); }, 220);
  previous?.focus?.();
  onClose?.();
}

/* ----------------------------------------------------------------- validation */

/** Wire live validation to a form.
 *
 *  Errors appear beside the field they belong to, and the submit button stays disabled
 *  until everything passes — rather than letting someone fill in a long form, press
 *  submit, and only then discover what was wrong.
 */
export function validate(form, rules, submitBtn) {
  const state = {};

  const check = (name) => {
    const input = form.querySelector(`[name="${name}"]`);
    if (!input) return true;
    const message = rules[name](input.value, form);
    const slot = form.querySelector(`[data-err="${name}"]`);
    state[name] = !message;
    input.setAttribute("aria-invalid", message ? "true" : "false");
    if (slot) slot.innerHTML = message ? `${icon("x", 12)}<span>${esc(message)}</span>` : "";
    return !message;
  };

  const refresh = () => {
    if (submitBtn) submitBtn.disabled = !Object.keys(rules).every((n) => state[n]);
  };

  for (const name of Object.keys(rules)) {
    const input = form.querySelector(`[name="${name}"]`);
    if (!input) continue;
    state[name] = !rules[name](input.value, form);
    // Validate on input, but only show the error once the field has been left — telling
    // someone their email is invalid while they are still typing it is just noise.
    input.addEventListener("blur", () => { check(name); refresh(); });
    input.addEventListener("input", () => {
      state[name] = !rules[name](input.value, form);
      if (input.getAttribute("aria-invalid") === "true") check(name);
      refresh();
    });
  }
  refresh();

  return {
    validateAll() {
      const ok = Object.keys(rules).map(check).every(Boolean);
      refresh();
      return ok;
    },
  };
}

export const rules = {
  required: (label) => (v) => (v && v.trim() ? "" : `${label} is required`),
  minLength: (n, label) => (v) => (v && v.trim().length >= n ? "" : `${label} must be at least ${n} characters`),
  email: () => (v) => (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v || "") ? "" : "That does not look like an email address"),
  password: () => (v) =>
    !v ? "A password is required"
    : v.length < 8 ? "At least 8 characters"
    : new Blob([v]).size > 72 ? "That is too long — 72 bytes maximum"
    : "",
  matches: (otherName, message) => (v, form) =>
    v === form.querySelector(`[name="${otherName}"]`)?.value ? "" : message,
};

/* ------------------------------------------------------------------- helpers */

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
