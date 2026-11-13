(() => {
  "use strict";
  const BUILD = "2026-11-13.4";            // shown with ?debug: tells which code a device really runs
  const DEBUG = /[?&#]debug\b/.test(location.search + location.hash);
  let dbgBox = null;
  function dbg(msg) {
    if (!DEBUG) return;
    console.info("[debug]", msg);
    if (!dbgBox) {
      dbgBox = document.createElement("pre");
      dbgBox.style.cssText = "position:fixed;left:8px;right:8px;bottom:8px;z-index:99;max-height:40vh;overflow:auto;" +
        "margin:0;padding:10px;background:rgba(0,0,0,.85);color:#9f9;font:12px/1.4 monospace;white-space:pre-wrap;border-radius:8px;user-select:text";
      document.body.appendChild(dbgBox);
    }
    dbgBox.textContent += (dbgBox.textContent ? "\n" : "") + new Date().toLocaleTimeString() + "  " + msg;
  }
  const C = window.INVITE_CONFIG || {};
  dbg("versión " + BUILD + " · endpoint " + (C.rsvpEndpoint ? "…" + C.rsvpEndpoint.slice(-26) : "(none: demo mode)"));
  dbg(navigator.userAgent);
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------ toast */
  const toastEl = $("#toast");
  let toastTimer;
  function toast(msg, ms = 3200) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), ms);
  }

  /* ------------------------------------------------------------ music */
  const audio = $("#song");
  const playBtn = $("#playBtn");
  const seek = $("#seek");
  let audioReady = false;
  let audioFailed = false;
  let seeking = false;

  if (C.song) {
    audio.src = C.song;
    audio.addEventListener("loadedmetadata", () => {
      audioReady = true;
      if (C.songStartAt && audio.currentTime < C.songStartAt) audio.currentTime = C.songStartAt;
    });
    audio.addEventListener("error", () => { audioFailed = true; });
  } else {
    audioFailed = true;
  }

  async function play(fromUser) {
    if (audioFailed) {
      if (fromUser) toast("Aún no se ha agregado la canción.");
      return;
    }
    try { await audio.play(); }
    catch (e) { if (fromUser) toast("No se pudo reproducir la canción."); }
  }
  function setPlaying(on) {
    document.body.classList.toggle("playing", on);
    playBtn.setAttribute("aria-label", on ? "Pausar" : "Reproducir");
  }
  audio.addEventListener("play", () => setPlaying(true));
  audio.addEventListener("pause", () => setPlaying(false));
  audio.addEventListener("ended", () => setPlaying(false));

  playBtn.addEventListener("click", () => (audio.paused ? play(true) : audio.pause()));
  $("#prevBtn").addEventListener("click", () => {
    if (!audioReady) return play(true);
    audio.currentTime = audio.currentTime < 3 ? 0 : Math.max(0, audio.currentTime - 10);
  });
  $("#nextBtn").addEventListener("click", () => {
    if (!audioReady) return play(true);
    audio.currentTime = Math.min(audio.duration - 0.5, audio.currentTime + 10);
  });

  function paintProgress(frac) {
    seek.style.setProperty("--p", (frac * 100).toFixed(2) + "%");
  }
  audio.addEventListener("timeupdate", () => {
    if (seeking || !audio.duration) return;
    const f = audio.currentTime / audio.duration;
    seek.value = Math.round(f * 1000);
    paintProgress(f);
  });
  seek.addEventListener("input", () => {
    seeking = true;
    paintProgress(seek.value / 1000);
  });
  seek.addEventListener("change", () => {
    if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration;
    seeking = false;
  });

  // Pause when the guest leaves the tab, resume when they come back.
  let resumeOnReturn = false;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { resumeOnReturn = !audio.paused; audio.pause(); }
    else if (resumeOnReturn) play(false);
  });

  // Heart
  const like = $("#likeBtn");
  like.addEventListener("click", () => {
    const on = like.getAttribute("aria-pressed") !== "true";
    like.setAttribute("aria-pressed", String(on));
  });

  // "+" = download the song
  const dl = $("#dlBtn");
  if (C.song) {
    dl.href = C.song;
    dl.setAttribute("download", C.songDownloadName || C.song.split("/").pop());
  } else {
    dl.addEventListener("click", (e) => { e.preventDefault(); toast("Aún no se ha agregado la canción."); });
  }

  /* ------------------------------------------------------------ calendar */
  const start = new Date(C.weddingDate);
  const end = new Date(start.getTime() + (C.calendar?.durationHours || 4) * 3600e3);
  const stamp = (d) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

  // .ics opens "Add to calendar" on iPhone/Mac/Outlook; Android opens it with the calendar app
  function downloadIcs() {
    if (isNaN(start)) return;
    const esc = (v) => String(v || "").replace(/([,;\\])/g, "\\$1");
    const ics = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Invitacion//ES", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
      "BEGIN:VEVENT",
      "UID:" + stamp(start) + "-boda@invitacion",
      "DTSTAMP:" + stamp(new Date()),
      "DTSTART:" + stamp(start), "DTEND:" + stamp(end),
      "SUMMARY:" + esc(C.calendar?.title || "Boda"),
      "LOCATION:" + esc(C.calendar?.location || ""),
      "URL:" + location.href.split("#")[0].split("?")[0],
      "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", "DESCRIPTION:Mañana es la boda", "END:VALARM",
      "END:VEVENT", "END:VCALENDAR",
    ].join("\r\n");
    const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "boda.ics" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  function googleCalendarUrl() {
    const q = new URLSearchParams({
      action: "TEMPLATE",
      text: C.calendar?.title || "Boda",
      dates: stamp(start) + "/" + stamp(end),
      location: C.calendar?.location || "",
      details: location.href.split("#")[0].split("?")[0],
    });
    return "https://calendar.google.com/calendar/render?" + q;
  }

  /* ------------------------------------------------------------ location modal */
  const maps = $("#mapsLink");
  if (maps && C.mapsUrl) maps.href = C.mapsUrl;
  const modal = $("#ubiModal");
  const modalImg = modal && $(".modal-photo", modal);
  const loadModalPhoto = () => { if (modalImg && !modalImg.src) modalImg.src = modalImg.dataset.src; };
  function openModal() {
    if (!modal || typeof modal.showModal !== "function") {     // very old browser: go straight to Maps
      if (C.mapsUrl) window.open(C.mapsUrl, "_blank", "noopener");
      return;
    }
    loadModalPhoto();
    modal.classList.remove("closing");
    modal.showModal();
    document.body.classList.add("modal-open");
  }
  function closeModal() {
    if (!modal || !modal.open || modal.classList.contains("closing")) return;
    modal.classList.add("closing");
    const done = () => { modal.classList.remove("closing"); modal.close(); document.body.classList.remove("modal-open"); };
    reduceMotion ? done() : setTimeout(done, 220);
  }
  if (modal) {
    $("#ubiBtn").addEventListener("click", openModal);
    $("#ubiClose").addEventListener("click", closeModal);
    modal.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(); });   // Esc key
    modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); }); // tap outside the card
    modal.addEventListener("close", () => document.body.classList.remove("modal-open"));
  }

  /* ------------------------------------------------------------ countdown */
  const cd = { d: $("#cd-d"), h: $("#cd-h"), m: $("#cd-m"), s: $("#cd-s") };
  const target = new Date(C.weddingDate).getTime();
  function tick() {
    let diff = Math.max(0, Math.floor((target - Date.now()) / 1000));
    const d = Math.floor(diff / 86400); diff -= d * 86400;
    const h = Math.floor(diff / 3600); diff -= h * 3600;
    const m = Math.floor(diff / 60);
    const s = diff - m * 60;
    const pad = (n) => String(n).padStart(2, "0");
    const vals = { d: String(d), h: String(h), m: pad(m), s: pad(s) };
    for (const k in vals) if (cd[k] && cd[k].textContent !== vals[k]) cd[k].textContent = vals[k];
  }
  if (!isNaN(target)) { tick(); setInterval(tick, 1000); }

  /* ------------------------------------------------------------ RSVP */
  const form = $("#rsvpForm");
  const nameInput = $("#rsvpName");
  const msg = $("#rsvpMsg");
  const submitBtn = $("#rsvpSubmit");
  const STORE = "rsvp-respuesta";

  const syncName = () => form.classList.toggle("has-name", nameInput.value.trim() !== "");
  nameInput.addEventListener("input", syncName);
  nameInput.addEventListener("focus", () => form.classList.add("focus-name"));
  nameInput.addEventListener("blur", () => form.classList.remove("focus-name"));

  function showMessage(html, withChange, withCalendar) {
    const cal = withCalendar && !isNaN(start)
      ? '<span class="actions"><button type="button" id="rsvpIcs">Agregar al calendario</button>' +
        '<a href="' + googleCalendarUrl() + '" target="_blank" rel="noopener">Google Calendar</a></span>'
      : "";
    msg.innerHTML = html + cal + (withChange ? '<button type="button" id="rsvpChange">Cambiar respuesta</button>' : "");
    form.classList.add("sent");
    const ics = $("#rsvpIcs");
    if (ics) ics.addEventListener("click", downloadIcs);
    const ch = $("#rsvpChange");
    if (ch) ch.addEventListener("click", () => {
      form.classList.remove("sent");
      try { localStorage.removeItem(STORE); } catch (e) {}
      nameInput.focus();
    });
  }
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function thanks(r) {
    const n = escapeHtml(r.nombre.split(" ")[0]);
    return r.asistencia === "si"
      ? `<strong>¡Gracias, ${n}!</strong>Nos hace muy felices que nos acompañes.`
      : `<strong>Gracias por avisarnos, ${n}.</strong>Te llevaremos en el corazón ese día.`;
  }

  const deadline = new Date(C.rsvpDeadline).getTime();
  const closed = !isNaN(deadline) && Date.now() > deadline;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) {}

  if (saved) showMessage(thanks(saved), !closed, saved.asistencia === "si");
  else if (closed) showMessage("<strong>El plazo para confirmar ha terminado.</strong>Si necesitas comunicarte con nosotros, escríbenos directamente.", false);

  function invalid(el, text) {
    el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake");
    toast(text);
  }

  // Sending an answer, in two steps:
  //  1) as a <script> request (JSONP): not subject to CORS, and the Apps Script replies
  //     {ok, error}, so we know the row was saved;
  //  2) if that can't load (e.g. the browser is signed into several Google accounts, or
  //     a work account, and Google answers with an error page), the same answer goes as
  //     an anonymous POST (no cookies, like an incognito window) in "no-cors" mode:
  //     it can't hit CORS errors, but the reply can't be read, so it's unconfirmed.
  function jsonp(url, r) {
    return new Promise((resolve, reject) => {
      const cb = "__rsvp" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
      const q = new URLSearchParams({ nombre: r.nombre, asistencia: r.asistencia, enviado: r.enviado, callback: cb });
      const tag = document.createElement("script");
      let timer;
      const done = () => { clearTimeout(timer); delete window[cb]; tag.remove(); };
      window[cb] = (data) => { done(); resolve(data); };
      tag.onerror = () => { done(); reject(new Error("script load failed")); };
      timer = setTimeout(() => { done(); reject(new Error("timeout")); }, 8000);
      tag.src = url + (url.includes("?") ? "&" : "?") + q;
      document.head.appendChild(tag);
    });
  }
  async function sendRsvp(url, r) {
    try {
      const data = await jsonp(url, r);
      dbg("1) script request → " + JSON.stringify(data));
      return data;                                    // {ok:false} = the script ran and said why: no retry
    } catch (err) {
      dbg("1) script request failed (" + err.message + ") → trying anonymous POST");
      console.warn("[RSVP] script request failed (" + err.message + "); sending anonymously instead");
    }
    try {
      await fetch(url, {
        method: "POST", mode: "no-cors", credentials: "omit",
        headers: { "Content-Type": "text/plain;charset=utf-8" },
        body: JSON.stringify(r),
      });
      dbg("2) anonymous POST → sent (Google's reply can't be read in this mode)");
      return { ok: true, unconfirmed: true };
    } catch (err) {
      dbg("2) anonymous POST failed (" + err.message + ")");
      console.error("[RSVP] Could not reach the Apps Script at all (network/blocked):", err);
      throw err;
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nombre = nameInput.value.trim().replace(/\s+/g, " ");
    const choice = form.querySelector('input[name="asistencia"]:checked');
    if (nombre.length < 2) { invalid($(".f-rsvp_linea"), "Por favor escribe tu nombre."); nameInput.focus(); return; }
    if (!choice) { invalid($(".f-rsvp_pregunta"), "Elige si nos acompañarás."); return; }

    const respuesta = { nombre, asistencia: choice.value, enviado: new Date().toISOString() };
    // Start the calendar download right away, while the tap still counts as a user
    // gesture: after waiting for the network, phones may silently block it.
    if (respuesta.asistencia === "si") downloadIcs();
    submitBtn.disabled = true;
    try {
      if (C.rsvpEndpoint) {
        const data = await sendRsvp(C.rsvpEndpoint, respuesta);
        if (!data || data.ok !== true) {
          console.error("[RSVP] The Apps Script answered but did not save:", data);
          throw new Error((data && data.error) || "not saved");
        }
      }
      try { localStorage.setItem(STORE, JSON.stringify(respuesta)); } catch (err) {}
      showMessage(thanks(respuesta), true, respuesta.asistencia === "si");
    } catch (err) {
      toast("No pudimos enviar tu respuesta. Revisa tu conexión e intenta de nuevo.");
    } finally {
      submitBtn.disabled = false;
    }
  });

  /* ------------------------------------------------------------ scroll reveals */
  function startReveals() {
    setTimeout(loadModalPhoto, 1500);      // fetch the modal photo once the page is showing
    const targets = [...$$(".sec"), ...$$(".reveal, .fade, .pop")];
    if (!("IntersectionObserver" in window)) { targets.forEach((t) => t.classList.add("in")); return; }
    const io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    targets.forEach((t) => io.observe(t));
  }

  /* ------------------------------------------------------------ intro */
  const intro = $("#intro");
  const sobre = $("#screenSobre");
  let opened = false;

  function openInvitation() {
    if (opened) return;
    opened = true;
    enableTransitions();
    play(false);                         // the tap is the gesture that allows audio
    // Timeline (ms from the tap): envelope opens, couple photo fades in (2.4 s),
    // stays, then the whole intro fades out (2.2 s, see .intro in the CSS).
    const D = reduceMotion ? 1600 : Math.max(3000, C.introDuration || 8650);
    const FADE_OUT = reduceMotion ? 400 : 2200;
    intro.classList.add("opening");
    timers.push(setTimeout(() => intro.classList.add("show-pareja"), 350));
    timers.push(setTimeout(() => leave(false), D - FADE_OUT));
    timers.push(setTimeout(() => intro.remove(), D + 50));
    // a tap on the couple photo skips ahead (handy for guests opening it again)
    timers.push(setTimeout(() => intro.addEventListener("click", () => leave(true), { once: true }), 900));
  }
  const timers = [];
  let left = false;
  function leave(skip) {
    if (left) return;
    left = true;
    if (skip) {
      timers.forEach(clearTimeout);
      intro.classList.add("skip");
      setTimeout(() => intro.remove(), 650);
    }
    window.scrollTo(0, 0);
    document.body.classList.remove("is-intro");
    intro.classList.add("leaving");
    startReveals();
  }
  // Transitions stay off until the page has loaded (see .preload in the CSS)
  function enableTransitions() {
    if (!document.documentElement.classList.contains("preload")) return;
    document.documentElement.classList.remove("preload");
    void document.body.offsetWidth;          // apply the change before any state class is added
  }
  if (document.readyState === "complete") requestAnimationFrame(() => requestAnimationFrame(enableTransitions));
  else addEventListener("load", () => requestAnimationFrame(() => requestAnimationFrame(enableTransitions)));

  sobre.addEventListener("click", openInvitation);
  sobre.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openInvitation(); }
  });
  sobre.focus({ preventScroll: true });

  // ?abrir in the URL skips the envelope (handy while editing)
  if (/[?&]abrir\b/.test(location.search)) {
    enableTransitions(); intro.remove(); document.body.classList.remove("is-intro"); startReveals();
  }
})();
