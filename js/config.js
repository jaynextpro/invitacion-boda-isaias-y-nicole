/* ==========================================================================
   Everything you are likely to change lives here.
   ========================================================================== */
window.INVITE_CONFIG = {
  // Ceremony date & time (El Salvador is UTC-06:00). Drives the countdown
  // and the calendar event offered when a guest accepts the invitation.
  weddingDate: "2026-12-27T15:30:00-06:00",   // 3:30 p.m., as in the location section

  // Last moment guests can RSVP (the design says "antes del 15 de diciembre de 2026").
  rsvpDeadline: "2026-12-15T23:59:59-06:00",

  // Where RSVP answers are sent. Leave "" to only store them in the guest's
  // browser (demo mode). Works with a Google Apps Script web-app URL
  // (see README) or any endpoint accepting a JSON POST.
  rsvpEndpoint: "",

  // "Ver ubicación" button. Paste the share link from Google Maps for an exact pin.
  mapsUrl: "https://maps.app.goo.gl/uHCUtP1yCXaCeUVP9",

  // Song for the player. Put your MP3 here (keep it under ~5 MB for fast loading).
  song: "assets/audio/contigo.mp3",
  songDownloadName: "Contigo - Los Panchos.mp3",   // file name when a guest taps "+"
  songStartAt: 0,          // seconds; skip a long intro if you like

  // Envelope -> couple photo -> page, total ms counted from the tap.
  // The photo fades in over 2.4 s and the intro fades out over 2.2 s; the rest
  // is time on the photo. Guests can tap the photo to skip ahead.
  introDuration: 8650,

  // Calendar event offered after a guest accepts (.ics + Google Calendar link).
  calendar: {
    title: "Boda Civil · Familia Guevara Cañas",
    location: "El Jardín Casa Rosada, Residencial Riverside, San Miguel, El Salvador",
    durationHours: 5,
  },
};
