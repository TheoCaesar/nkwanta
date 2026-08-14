/* Reporting an incident.
 *
 * NFR-3: the system must never ask anyone to type while driving. So the fastest path
 * through this form is three taps and a spoken sentence — type, location from GPS, hold
 * to speak. Typing is available and never required.
 *
 * The recorder enforces its own limit rather than letting someone speak for two minutes
 * and then rejecting the upload. It warns at 80% and stops at the cap.
 */

import { submitReport } from "../api.js";
import { go } from "../router.js";
import { refreshIncidents, refreshQueue } from "../store.js";
import { esc, icon, kb, rules, toast, validate } from "../ui.js";

const MAX_VOICE = 512 * 1024;
const MAX_PHOTO = 256 * 1000;
const WARN_AT = 0.8;

const TYPES = [
  ["accident", "Accident"], ["flood", "Flooding"], ["closure", "Road closure"],
  ["signal_outage", "Lights out"], ["roadworks", "Roadworks"], ["surface_defect", "Bad surface"],
];

const photoPicker = () => `
  <label class="btn btn--ghost btn--sm" style="cursor:pointer">
    ${icon("camera",16)} Add a photo
    <input type="file" accept="image/jpeg,image/png,image/webp" id="photo" hidden>
  </label>`;

export default function reportView(mount) {
  let chosenType = null;
  let position = null;
  let photo = null;
  let voice = null;
  let recorder = null;
  let stream = null;
  let sizeTimer = null;
  let voiceUrl = null;
  let warned = false;

  mount.innerHTML = `
    <div class="scroll pad">
      <form id="f" class="card" style="max-width:520px;margin:0 auto" novalidate>
        <h2>Report an incident</h2>

        <div class="field">
          <label id="typeLabel">What is blocking the road <span class="req">*</span></label>
          <div class="chips" role="group" aria-labelledby="typeLabel">
            ${TYPES.map(([v, l]) =>
              `<button type="button" class="chip" data-type="${esc(v)}" aria-pressed="false">${esc(l)}</button>`
            ).join("")}
          </div>
          <input type="hidden" name="incident_type">
          <div class="err" data-err="incident_type"></div>
        </div>

        <div class="field" style="margin-top:16px">
          <label>Where <span class="req">*</span></label>
          <div class="inline">
            <button type="button" class="btn btn--ghost btn--sm" id="gps">${icon("pin",16)} Use my location</button>
            <a class="btn btn--ghost btn--sm" href="#/">Pick on the map</a>
          </div>
          <input type="hidden" name="location">
          <div class="hint" id="where">No location yet. Your phone's location is quickest.</div>
          <div class="err" data-err="location"></div>
        </div>

        <div class="field" style="margin-top:16px">
          <label for="note">Note <span class="faint">· optional</span></label>
          <textarea class="input" id="note" name="note" maxlength="500"
                    placeholder="Two lanes blocked, backed up to Odorna"></textarea>
          <div class="counter"><span id="noteCount">0</span> / 500</div>
        </div>

        <div class="field" style="margin-top:8px">
          <label>Photograph <span class="faint">· optional</span></label>
          <div id="photoBox">${photoPicker()}</div>
          <div class="hint">Up to ${Math.round(MAX_PHOTO/1000)} KB. Large photos are refused rather than silently shrunk.</div>
        </div>

        <div class="field" style="margin-top:16px">
          <label>Voice note <span class="faint">· optional</span></label>
          <div class="card card--flat" style="padding:12px">
            <div class="row-between">
              <button type="button" class="btn btn--ghost btn--sm" id="rec">${icon("mic",16)} Hold to speak</button>
              <span class="xs num" id="meter">0 / ${Math.round(MAX_VOICE/1024)} KB</span>
            </div>
            <div class="bar" style="margin-top:8px"><i id="meterBar" style="width:0"></i></div>
            <div class="hint" id="recHint">Recording stops by itself at the limit. You will be warned at 80%.</div>
            <div id="voicePreview"></div>
          </div>

          <label class="check" style="margin-top:12px">
            <input type="checkbox" id="share">
            <span>Let other commuters hear this recording</span>
          </label>
          <div class="hint" style="padding-left:26px">
            Off by default. A recording identifies your voice. Officers can always hear it;
            other commuters only if you allow it, and you can change this later.
          </div>
        </div>

        <button class="btn btn--block" id="submit" style="margin-top:20px" disabled>Submit report</button>
        <p class="hint center" style="margin-top:10px">
          Never type while driving. Hand the phone to a passenger, or hold the record button and speak.
        </p>
      </form>
    </div>`;

  const form = mount.querySelector("#f");
  const submit = mount.querySelector("#submit");

  const v = validate(form, {
    incident_type: rules.required("An incident type"),
    location: rules.required("A location"),
  }, submit);

  /* ------------------------------------------------------------- type chips */
  mount.querySelectorAll("[data-type]").forEach((chip) => {
    chip.addEventListener("click", () => {
      chosenType = chip.dataset.type;
      mount.querySelectorAll("[data-type]").forEach(c =>
        c.setAttribute("aria-pressed", String(c === chip)));
      form.incident_type.value = chosenType;
      form.incident_type.dispatchEvent(new Event("input"));
    });
  });

  /* --------------------------------------------------------------- location */
  mount.querySelector("#gps").addEventListener("click", () => {
    if (!navigator.geolocation) return toast("This browser cannot report a location", { error: true });
    mount.querySelector("#where").textContent = "Finding you…";
    navigator.geolocation.getCurrentPosition(
      (p) => setPosition(p.coords.latitude, p.coords.longitude, Math.round(p.coords.accuracy)),
      () => {
        mount.querySelector("#where").textContent =
          "Location permission refused. Open the map and long-press where it happened.";
        toast("Could not get your location", { error: true });
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });

  function setPosition(lat, lon, accuracy) {
    position = { lat, lon };
    form.location.value = `${lat},${lon}`;
    form.location.dispatchEvent(new Event("input"));
    mount.querySelector("#where").textContent =
      `Set to ${lat.toFixed(5)}, ${lon.toFixed(5)}${accuracy ? ` · within about ${accuracy} m` : ""}`;
  }

  /* ------------------------------------------------------------------- note */
  form.note.addEventListener("input", () => {
    mount.querySelector("#noteCount").textContent = form.note.value.length;
  });

  /* ------------------------------------------------------------------ photo
   *
   * Nobody should have to submit a report to find out what they attached. The chosen
   * file is shown full size, from a local object URL — no upload, no round trip — so the
   * decision to keep or replace it is made before anything is sent.
   *
   * The listener is delegated to the container rather than bound to the input, because
   * removing a photograph replaces that input with a new one. Binding directly meant the
   * second attempt at choosing a photograph silently did nothing.
   */
  const photoBox = mount.querySelector("#photoBox");
  let photoUrl = null;

  photoBox.addEventListener("change", (e) => {
    if (e.target.id !== "photo") return;
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_PHOTO) {
      toast(`That photo is ${kb(file.size)}. The limit is ${Math.round(MAX_PHOTO/1000)} KB.`,
            { type: "warning" });
      e.target.value = "";
      return;
    }
    photo = file;
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(file);
    photoBox.innerHTML = `
      <figure style="margin:0">
        <img src="${photoUrl}" alt="The photograph you are about to send"
             style="width:100%;max-height:220px;object-fit:contain;background:var(--grey-100);
                    border-radius:var(--r-sm);display:block">
        <figcaption class="row-between" style="margin-top:8px">
          <span class="xs">${esc(kb(file.size))} · check it shows what you mean</span>
          <span class="inline">
            <label class="btn btn--ghost btn--sm" style="cursor:pointer">Replace
              <input type="file" accept="image/jpeg,image/png,image/webp" id="photo" hidden></label>
            <button type="button" class="btn btn--ghost btn--sm" id="dropPhoto">Remove</button>
          </span>
        </figcaption>
      </figure>`;
  });

  photoBox.addEventListener("click", (e) => {
    if (e.target.closest("#dropPhoto") === null) return;
    photo = null;
    if (photoUrl) { URL.revokeObjectURL(photoUrl); photoUrl = null; }
    photoBox.innerHTML = photoPicker();
  });

  /* ------------------------------------------------------------------ voice */
  const recBtn = mount.querySelector("#rec");
  const meter = mount.querySelector("#meter");
  const meterBar = mount.querySelector("#meterBar");
  const recHint = mount.querySelector("#recHint");

  recBtn.addEventListener("click", async () => {
    if (recorder?.state === "recording") { recorder.stop(); return; }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      let bytes = 0;
      warned = false;
      recorder = new MediaRecorder(stream);

      recorder.ondataavailable = (e) => {
        chunks.push(e.data);
        bytes += e.data.size;
        const pct = Math.min(100, Math.round((bytes / MAX_VOICE) * 100));
        meter.textContent = `${Math.round(bytes/1024)} / ${Math.round(MAX_VOICE/1024)} KB`;
        meterBar.style.width = `${pct}%`;

        if (!warned && bytes > MAX_VOICE * WARN_AT) {
          warned = true;
          recHint.textContent = "Nearly at the limit — finish your sentence.";
          recHint.style.color = "var(--amber-700)";
        }
        // Stop ourselves rather than let the upload be rejected afterwards.
        if (bytes >= MAX_VOICE && recorder.state === "recording") recorder.stop();
      };

      recorder.onstop = () => {
        voice = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach(t => t.stop());
        clearInterval(sizeTimer);
        recBtn.innerHTML = `${icon("mic",16)} Record again`;
        recHint.textContent = `Recorded ${kb(voice.size)}. Play it back before you send it.`;
        recHint.style.color = "";
        showVoicePreview();
      };

      // Timeslice so ondataavailable fires while recording, not only at the end —
      // otherwise the meter would sit at zero and the cap could never be enforced live.
      recorder.start(500);
      recBtn.innerHTML = `${icon("x",16)} Stop`;
      recHint.textContent = "Recording… say what is blocking the road and where.";
    } catch {
      toast("Microphone unavailable. A written note works too.", { error: true });
    }
  });

  /* Hear it before anybody else does. A recording made on a phone in traffic is as
   * likely to be wind noise as speech, and the recorder is the only person who can tell.
   * Played from a local object URL, so this works with no connection at all. */
  function showVoicePreview() {
    if (voiceUrl) URL.revokeObjectURL(voiceUrl);
    voiceUrl = URL.createObjectURL(voice);
    mount.querySelector("#voicePreview").innerHTML = `
      <audio controls preload="metadata" src="${voiceUrl}"
             style="width:100%;height:34px;margin-top:10px"></audio>
      <button type="button" class="btn btn--ghost btn--sm" id="dropVoice"
              style="margin-top:8px">Discard recording</button>`;
    mount.querySelector("#dropVoice").addEventListener("click", () => {
      voice = null;
      URL.revokeObjectURL(voiceUrl); voiceUrl = null;
      mount.querySelector("#voicePreview").innerHTML = "";
      meter.textContent = `0 / ${Math.round(MAX_VOICE/1024)} KB`;
      meterBar.style.width = "0";
      recBtn.innerHTML = `${icon("mic",16)} Hold to speak`;
      recHint.textContent = "Recording stops by itself at the limit. You will be warned at 80%.";
    });
  }

  /* ----------------------------------------------------------------- submit */
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!v.validateAll()) return;

    submit.disabled = true;
    submit.textContent = "Sending…";
    try {
      const result = await submitReport({
        body: {
          incident_type: chosenType,
          latitude: position.lat,
          longitude: position.lon,
          note: form.note.value.trim() || null,
        },
        photo, voice,
        shareVoice: mount.querySelector("#share").checked,
      });

      if (result.queued) {
        toast("No signal — your report is saved and will send by itself.");
        refreshQueue();
      } else if (result.duplicate) {
        toast("You had already sent that report.");
      } else if (result.rejected?.length) {
        // The report itself was accepted; the evidence was not. Say which, and say that
        // the report stands — otherwise the user cannot tell what actually happened.
        toast(`Reported, but your ${result.rejected.join(" and ")} could not be attached.`,
              { type: "warning" });
        setTimeout(() => refreshIncidents().catch(() => {}), 2500);
      } else {
        toast("Reported. Thank you.", { type: "success" });
        setTimeout(() => refreshIncidents().catch(() => {}), 2500);
      }
      go("/");
    } catch (err) {
      toast(err.message, { error: true });
      submit.disabled = false;
      submit.textContent = "Submit report";
    }
  });

  return {
    destroy() {
      clearInterval(sizeTimer);
      if (recorder?.state === "recording") recorder.stop();
      stream?.getTracks().forEach(t => t.stop());
      // An object URL holds its blob in memory until it is revoked.
      if (photoUrl) URL.revokeObjectURL(photoUrl);
      if (voiceUrl) URL.revokeObjectURL(voiceUrl);
    },
  };
}
