/* The map, and the incident list beneath it.
 *
 * Open to everyone, signed in or not: a commuter checking the road ahead should not have
 * to create an account first.
 *
 * The map is treated as an enhancement, not a dependency. MapLibre loads from a CDN and
 * tiles come from OpenStreetMap; either can fail on a poor connection — which is
 * precisely the connection this system's users have. If it fails, the list below carries
 * the same information and the view still works.
 */

import { api, auth } from "../api.js";
import { refreshIncidents, state, subscribe } from "../store.js";
import {
  LABEL, STATUS_COLOUR, TYPE_LABEL, ago, avatar, empty, errorState,
  esc, icon, pct, sheet, skeleton, toast,
} from "../ui.js";

const ACCRA = [-0.187, 5.603];

export default function mapView(mount) {
  /* Signed out, the map is the whole page — D-044.
   *
   * No list beneath it, because the list is a table of things the visitor cannot open;
   * no tab bar, because the shell removes it. What is left is the road, a legend and a
   * count, which is everything the public map ever promised. */
  const open = !auth.signedIn;

  mount.innerHTML = `
    <div id="map" role="img" aria-label="Map of current incidents in Greater Accra"></div>
    ${open ? `
      <div class="hero">
        <div class="hero__eyebrow"><i class="hero__live"></i> Greater Accra \u00b7 live</div>
        <h1>Know the traffic situation before you leave</h1>
        <p>Accidents, floods and closures, reported by the people sitting in them \u2014
           and checked against each other before you are warned.</p>
        <div class="hero__count" id="count"></div>
        <div class="hero__cta">
          <a class="btn btn--onmap" href="#/register">Create an account</a>
          <a class="btn btn--onmap" href="#/signin">Sign in</a>
        </div>
      </div>
      <div class="maplegend">
        ${legend("verified", "verified")}
        ${legend("corroborated", "corroborated")}
        ${legend("reported", "unconfirmed")}
      </div>` : `
    <div class="scroll" style="flex:0 1 auto;max-height:46%;background:var(--canvas)">
      <div class="pad" style="padding-bottom:8px">
        <div class="row-between">
          <h2>Current Incidents</h2>
          <span class="xs num" id="count"></span>
        </div>
        <div class="inline centerCap xs" style="margin-top:8px;gap:14px">
          ${legend("verified", "verified")}
          ${legend("corroborated", "corroborated")}
          ${legend("reported", "unconfirmed")}
          ${legend("assigned", "warden sent")}
        </div>
      </div>
      <div class="pad" style="padding-top:0"><div class="list" id="list">${skeleton(3)}</div></div>
    </div>`}`;

  if (open) mount.style.position = "relative";

  let map = null;
  let markers = [];

  initMap();
  render(state.incidents);
  const unsubscribe = subscribe((s) => render(s.incidents));
  refreshIncidents().catch(showError);

  function legend(status, label) {
    return `<span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;
            background:${STATUS_COLOUR[status]};margin-right:5px"></i>${esc(label)}</span>`;
  }

  function initMap() {
    const el = mount.querySelector("#map");
    if (typeof maplibregl === "undefined") { degrade(el); return; }
    try {
      map = new maplibregl.Map({
        container: el,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            },
          },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        },
        center: ACCRA,
        zoom: 10.6,
      });
      // Signed out the zoom control moves to the bottom, because the top of the map is
      // under the hero's scrim — a dark gradient over a white control is unreadable, and
      // the hero passes taps through, so it would be usable and invisible at once.
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }),
                     open ? "bottom-right" : "top-right");
      map.on("error", () => {/* a missing tile must not take the view down */});
    } catch {
      degrade(el);
    }
  }

  function degrade(el) {
    // The map is an enhancement. If the library or its tiles cannot load — on exactly
    // the connection this system's users have — the list takes the whole view and
    // carries the same information.
    const list = mount.querySelector(".scroll");
    if (!list) {
      // Signed out there is no list to fall back to, so say so in the space the map
      // would have used. An empty grey rectangle is not a degraded map, it is a bug.
      el.innerHTML = `<div class="pad center" style="margin:auto;max-width:280px">
        ${empty("The map could not load",
                "Your connection may be too slow for it. Sign in to see the list instead.")}
        <a class="btn btn--block" href="#/signin" style="margin-top:12px">Sign in</a>
      </div>`;
      el.style.display = "flex";
      return;
    }
    el.style.flex = "0 0 auto";
    el.style.minHeight = "0";
    el.style.height = "0";
    list.style.maxHeight = "none";
    list.style.flex = "1 1 auto";
  }

  function render(incidents) {
    const count = mount.querySelector("#count");
    if (count && open) {
      /* The headline's claim, evidenced immediately underneath it by real data.
       *
       * A marketing banner over a live map that says nothing the map does not already
       * say is decoration. This is the one number a visitor came for, and it is the same
       * number the markers add up to — so the hero is part of the interface rather than
       * a poster stuck on the front of it. */
      const verified = incidents.filter(i => i.status === "verified").length;
      count.innerHTML = incidents.length
        ? `<span><b>${incidents.length}</b> on the road right now</span>
           ${verified ? `<span class="tag tag--verified">${verified} verified</span>` : ""}`
        : `<span>Nothing reported right now \u2014 the roads are clear,
             or nobody has said otherwise yet.</span>`;
    } else if (count) {
      count.textContent = incidents.length ? `${incidents.length} shown` : "";
    }
    drawPins(incidents);

    const list = mount.querySelector("#list");
    if (!list) return;
    if (!incidents.length) {
      list.innerHTML = empty("Nothing reported", "The roads are clear, or nobody has said otherwise yet.");
      return;
    }
    list.innerHTML = incidents.map(inc => `
      <button class="row-between" data-id="${esc(inc.id)}"
              style="width:100%;background:none;border:0;text-align:left;cursor:pointer;padding:12px 0">
        <span class="grow">
          <span class="t">${esc(TYPE_LABEL[inc.incident_type] ?? inc.incident_type)}</span>
          <span class="m">${inc.report_count} report${inc.report_count === 1 ? "" : "s"}
            · ${esc(ago(inc.last_reported_at))}</span>
          <span class="bar" style="width:120px;margin-top:6px"><i style="width:${Math.floor(inc.confidence*100)}%"></i></span>
        </span>
        <span style="text-align:right">
          <span class="tag tag--${esc(inc.status)}">${esc(inc.status.replace("_"," "))}</span>
          <span class="m num">${pct(inc.confidence)}</span>
        </span>
      </button>`).join("");

    list.querySelectorAll("[data-id]").forEach(btn =>
      btn.addEventListener("click", () => openDetail(btn.dataset.id)));
  }

  function drawPins(incidents) {
    if (!map) return;
    markers.forEach(m => m.remove());
    markers = incidents.map(inc => {
      // Signed out, `confidence` is withheld, so size follows status instead of the
      // score. The three statuses are the score banded at 0.35 and 0.70 — the same
      // grammar at three steps rather than continuous.
      const size = open
        ? ({ reported: 16, corroborated: 24, verified: 32, assigned: 30 }[inc.status] ?? 18)
        : 14 + Math.round(inc.confidence * 22);
      const el = document.createElement("button");
      el.setAttribute("aria-label", open
        ? `${TYPE_LABEL[inc.incident_type]}, ${inc.status.replace("_", " ")}`
        : `${TYPE_LABEL[inc.incident_type]}, ${LABEL.confidence.toLowerCase()} ${pct(inc.confidence)}`);
      el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;cursor:pointer;
        background:${STATUS_COLOUR[inc.status] ?? "#888"};border:2px solid rgba(255,255,255,.92);
        box-shadow:0 1px 4px rgba(0,0,0,.3);padding:0`;
      el.addEventListener("click", () => openDetail(inc.id));
      return new maplibregl.Marker({ element: el })
        .setLngLat([inc.longitude, inc.latitude]).addTo(map);
    });
  }

  async function openDetail(id) {
    sheet({
      title: "Incident",
      body: `<div class="list">${skeleton(4)}</div>`,
      onMount: async (el) => {
        try {
          const inc = await api(`/incidents/${id}`);
          el.querySelector(".sheet__body").innerHTML = open ? teaserHtml(inc) : detailHtml(inc);
          if (!open) wireEvidence(el);
        } catch (err) {
          el.querySelector(".sheet__body").innerHTML = errorState(err.message);
        }
      },
    });
  }

  /* What a signed-out visitor gets — D-044.
   *
   * The answer comes first and costs nothing: what is blocking the road, roughly where,
   * and how long ago. Only then does it say what an account adds, and it says it in the
   * visitor's words rather than the system's — "photographs and spoken reports", not
   * "evidence attachments"; "how accurate this is", not "confidence score".
   *
   * The list of what is locked is deliberately concrete. "Sign in for more" asks somebody
   * to pay a price for an unnamed thing; naming the three lets them decide it is not
   * worth it, which is a fair outcome and a more honest ask. */
  function teaserHtml(inc) {
    return `
      <div class="row-between" style="margin-bottom:4px">
        <h2 style="font-size:17px">${esc(TYPE_LABEL[inc.incident_type] ?? inc.incident_type)}</h2>
        <span class="tag tag--${esc(inc.status)}">${esc(inc.status.replace("_"," "))}</span>
      </div>
      <p class="m">Last reported ${esc(ago(inc.last_reported_at))}</p>

      <div class="locked">
        <div class="inline xs" style="gap:6px;color:var(--faint);margin-bottom:8px">
          ${icon("lock",14)}
          <span style="text-transform:uppercase;letter-spacing:.06em;font-weight:600">Needs an account</span>
        </div>
        <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.9;color:var(--muted)">
          <li>Who reported it, and how reliable they are</li>
          <li>Photographs and spoken reports</li>
          <li>How accurate this is, and why</li>
        </ul>
      </div>

      <a class="btn btn--block" href="#/signin" style="margin-top:14px">Sign in to see the detail</a>
      <a class="btn btn--ghost btn--block" href="#/register" style="margin-top:8px">Create an account</a>
      <p class="hint center" style="margin:10px 0 20px">
        An account also lets you report, and warns you about your own routes.
      </p>`;
  }

  function detailHtml(inc) {
    const evidence = inc.evidence.map((e, i) => {
      const photos = e.attachments.filter(a => a.kind === "photo");
      const voice  = e.attachments.filter(a => a.kind === "voice");
      const hasDetail = Boolean(e.note) || e.attachments.length > 0;

      const summary = [
        e.note ? "note" : null,
        photos.length ? `${photos.length} photo${photos.length > 1 ? "s" : ""}` : null,
        voice.length ? "voice" : null,
      ].filter(Boolean).join(" \u00b7 ");

      return `
        <div>
          <button data-report="${i}" aria-expanded="false" ${hasDetail ? "" : "disabled"}
                  class="row-between" style="width:100%;background:none;border:0;
                  text-align:left;padding:10px 0;cursor:${hasDetail ? "pointer" : "default"}">
            <span class="inline grow">
              ${avatar(e.reporter_name, e.report_id, 30)}
              <span class="grow">
                <span class="t" style="font-size:13px">${esc(e.reporter_name)}</span>
                <span class="m">${esc(LABEL.reputation.toLowerCase())} ${pct(e.reporter_reputation)}
                  \u00b7 ${esc(ago(e.occurred_at))}</span>
              </span>
            </span>
            <span class="xs" style="white-space:nowrap;color:${hasDetail ? "var(--green)" : "var(--faint)"}">
              ${esc(summary || "no detail")}
            </span>
          </button>

          <div class="hide" data-detail="${i}" style="padding:0 0 14px 42px">
            ${e.note ? `<p style="font-size:13.5px;margin:0 0 10px;line-height:1.5">
              \u201c${esc(e.note)}\u201d</p>` : ""}

            ${photos.length ? `<div class="inline" style="gap:8px;margin-bottom:10px">
              ${photos.map(p => `<a href="${esc(p.url)}" target="_blank" rel="noopener"
                  style="display:block;width:78px;height:78px;border-radius:var(--r-sm);
                         overflow:hidden;background:var(--grey-100)">
                  <img src="${esc(p.url)}" loading="lazy"
                       alt="Photograph attached by ${esc(e.reporter_name)}"
                       style="width:100%;height:100%;object-fit:cover"></a>`).join("")}
            </div>` : ""}

            ${voice.map(v => `
              <div class="card card--flat" style="padding:10px;margin-bottom:8px">
                <div class="inline" style="margin-bottom:7px">
                  ${icon("mic", 15)}
                  <span class="xs grow">Spoken report${v.duration_seconds
                    ? ` \u00b7 ${Math.round(v.duration_seconds)}s` : ""}</span>
                  ${v.is_public ? "" : `<span class="tag tag--reported">not shared</span>`}
                </div>
                <audio controls preload="none" src="${esc(v.url)}"
                       style="width:100%;height:34px"></audio>
              </div>`).join("")}

            <p class="xs faint" style="margin:6px 0 0">
              Contributed ${pct(e.weight / 0.45)} of what one report can ever count for.
            </p>
          </div>
        </div>`;
    }).join("");

    return `
      <div class="row-between" style="margin-bottom:4px">
        <h2 style="font-size:17px">${esc(TYPE_LABEL[inc.incident_type])}</h2>
        <span class="tag tag--${esc(inc.status)}">${esc(inc.status.replace("_"," "))}</span>
      </div>
      <p class="m">Grouped from ${inc.report_count} report${inc.report_count === 1 ? "" : "s"}
         within 300 m and 30 minutes</p>

      <div class="inline" style="margin:16px 0">
        <span class="xs" style="min-width:74px">${esc(LABEL.confidence)}</span>
        <span class="bar grow"><i style="width:${Math.floor(inc.confidence*100)}%"></i></span>
        <strong class="num">${pct(inc.confidence)}</strong>
      </div>

      <h3 style="margin-bottom:2px">Who reported it</h3>
      <p class="xs faint" style="margin:0 0 4px">Tap a reporter to see what they sent.</p>
      <div class="list">${evidence}</div>

      <p class="hint" style="margin:16px 0 24px;background:var(--grey-100);padding:10px 12px;border-radius:var(--r-sm)">
        Each report counts for its reporter\u2019s ${esc(LABEL.reputation.toLowerCase())},
        reduced by how long ago it was made \u2014 the half-life is 45 minutes. An incident
        nobody confirms fades off the map on its own.
      </p>`;
  }

  /** Let a reporter row open to show the note, photographs and recording they sent. */
  function wireEvidence(root) {
    root.querySelectorAll("[data-report]").forEach((btn) => {
      const detail = root.querySelector(`[data-detail="${btn.dataset.report}"]`);
      if (!detail || !detail.children.length) return;
      btn.addEventListener("click", () => {
        const closed = detail.classList.toggle("hide");
        btn.setAttribute("aria-expanded", String(!closed));
      });
    });
  }

  function showError(err) {
    mount.querySelector("#list").innerHTML = errorState(err.message, "retry");
    mount.querySelector('[data-action="retry"]')
      ?.addEventListener("click", () => refreshIncidents().catch(showError));
  }

  return {
    destroy() {
      unsubscribe();
      markers.forEach(m => m.remove());
      map?.remove();
    },
  };
}
