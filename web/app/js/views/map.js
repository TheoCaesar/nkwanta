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

import { api } from "../api.js";
import { refreshIncidents, state, subscribe } from "../store.js";
import {
  STATUS_COLOUR, TYPE_LABEL, ago, avatar, empty, errorState,
  esc, icon, sheet, skeleton, toast,
} from "../ui.js";

const ACCRA = [-0.187, 5.603];

export default function mapView(mount) {
  mount.innerHTML = `
    <div id="map" role="img" aria-label="Map of current incidents in Greater Accra"></div>
    <div class="scroll" style="flex:0 1 auto;max-height:46%;background:var(--canvas)">
      <div class="pad" style="padding-bottom:8px">
        <div class="row-between">
          <h2>Current incidents</h2>
          <span class="xs num" id="count"></span>
        </div>
        <div class="inline xs" style="margin-top:8px;gap:14px">
          ${legend("verified", "verified")}
          ${legend("corroborated", "corroborated")}
          ${legend("reported", "unconfirmed")}
          ${legend("assigned", "warden sent")}
        </div>
      </div>
      <div class="pad" style="padding-top:0"><div class="list" id="list">${skeleton(3)}</div></div>
    </div>`;

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
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("error", () => {/* a missing tile must not take the view down */});
    } catch {
      degrade(el);
    }
  }

  function degrade(el) {
    // The map is an enhancement. If the library or its tiles cannot load — on exactly
    // the connection this system's users have — the list takes the whole view and
    // carries the same information.
    el.style.flex = "0 0 auto";
    el.style.minHeight = "0";
    el.style.height = "0";
    const list = mount.querySelector(".scroll");
    list.style.maxHeight = "none";
    list.style.flex = "1 1 auto";
  }

  function render(incidents) {
    mount.querySelector("#count").textContent =
      incidents.length ? `${incidents.length} shown` : "";
    drawPins(incidents);

    const list = mount.querySelector("#list");
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
          <span class="bar" style="width:120px;margin-top:6px"><i style="width:${Math.round(inc.confidence*100)}%"></i></span>
        </span>
        <span style="text-align:right">
          <span class="tag tag--${esc(inc.status)}">${esc(inc.status.replace("_"," "))}</span>
          <span class="m num">${inc.confidence.toFixed(2)}</span>
        </span>
      </button>`).join("");

    list.querySelectorAll("[data-id]").forEach(btn =>
      btn.addEventListener("click", () => openDetail(btn.dataset.id)));
  }

  function drawPins(incidents) {
    if (!map) return;
    markers.forEach(m => m.remove());
    markers = incidents.map(inc => {
      const size = 14 + Math.round(inc.confidence * 22);
      const el = document.createElement("button");
      el.setAttribute("aria-label",
        `${TYPE_LABEL[inc.incident_type]}, confidence ${inc.confidence.toFixed(2)}`);
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
          el.querySelector(".sheet__body").innerHTML = detailHtml(inc);
        } catch (err) {
          el.querySelector(".sheet__body").innerHTML = errorState(err.message);
        }
      },
    });
  }

  function detailHtml(inc) {
    const evidence = inc.evidence.map(e => `
      <div class="row-between">
        <span class="inline">
          ${avatar(e.reporter_name, e.report_id, 28)}
          <span>
            <span class="t" style="font-size:13px">${esc(e.reporter_name)}</span>
            <span class="m">reputation ${e.reporter_reputation.toFixed(2)} · ${esc(ago(e.occurred_at))}</span>
          </span>
        </span>
        <span class="num" style="font-size:13px">${e.weight.toFixed(3)}</span>
      </div>`).join("");

    return `
      <div class="row-between" style="margin-bottom:4px">
        <h2 style="font-size:17px">${esc(TYPE_LABEL[inc.incident_type])}</h2>
        <span class="tag tag--${esc(inc.status)}">${esc(inc.status.replace("_"," "))}</span>
      </div>
      <p class="m">Grouped from ${inc.report_count} report${inc.report_count === 1 ? "" : "s"}
         within 300 m and 30 minutes</p>

      <div class="inline" style="margin:16px 0">
        <span class="xs" style="min-width:72px">Confidence</span>
        <span class="bar grow"><i style="width:${Math.round(inc.confidence*100)}%"></i></span>
        <strong class="num">${inc.confidence.toFixed(2)}</strong>
      </div>

      <h3 style="margin-bottom:6px">Who reported it</h3>
      <div class="list">${evidence}</div>

      <p class="hint" style="margin:16px 0 24px;background:var(--grey-100);padding:10px 12px;border-radius:var(--r-sm)">
        Each report counts for its reporter's reliability, reduced by how long ago it was made —
        the half-life is 45 minutes. An incident nobody confirms fades off the map on its own.
      </p>`;
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
