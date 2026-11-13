/**
 * RSVP receiver for the wedding invitation (Google Apps Script web app).
 *
 * Setup (README → "2. Collect RSVPs in a Google Sheet"):
 *  1. Paste this whole file into Apps Script (replace everything).
 *  2. Put your spreadsheet's ID in SHEET_ID (from its URL: /spreadsheets/d/<ID>/edit).
 *  3. Deploy → Manage deployments → ✏️ Edit → Version: "New version" → Deploy
 *     Execute as: Me · Who has access: Anyone   (exactly "Anyone")
 *  4. Open the /exec URL in a private/incognito window: it must show {"ok":true,...}
 *
 * How the page talks to it (and why): the page loads
 *   /exec?nombre=…&asistencia=si|no&callback=fn
 * as a <script>. Browsers never apply CORS to script loads, so Google's redirects and
 * cross-domain replies can't block it (fetch() from your domain hit "CORS policy"
 * errors on some devices). The script answers with JavaScript: fn({"ok":true}),
 * which is how the page knows the row was really saved.
 */

const SHEET_ID = 'PEGA_AQUI_EL_ID_DE_TU_HOJA';  // e.g. 1AbC...xyz (only optional if the script was created from the sheet)
const SHEET_NAME = '';                          // tab name; empty = first tab
const HEADERS = ['fecha', 'nombre', 'asistencia'];

function doGet(e) {
  const p = (e && e.parameter) || {};
  const result = (p.nombre || p.asistencia) ? save_(p) : health_();
  // JSONP reply for the page; plain JSON when opened directly in a browser
  const cb = String(p.callback || '');
  if (/^[A-Za-z_$][\w$]{0,63}$/.test(cb)) {          // only a plain function name: nothing else can be injected
    return ContentService.createTextOutput(cb + '(' + JSON.stringify(result) + ');')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return json_(result);
}

function doPost(e) {
  // still accepted (JSON body or form fields), e.g. for testing with curl
  let data = (e && e.parameter) || {};
  if (e && e.postData && e.postData.contents) {
    try { data = JSON.parse(e.postData.contents); } catch (_) {}
  }
  return json_(save_(data));
}

function save_(data) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);   // two guests answering at once can't overwrite each other
    const nombre = String(data.nombre || '').trim().slice(0, 120);
    const asistencia = data.asistencia === 'si' ? 'Sí' : data.asistencia === 'no' ? 'No' : '';
    if (!nombre || !asistencia) return { ok: false, error: 'Faltan datos (nombre/asistencia)' };
    const sheet = getSheet_();
    if (sheet.getLastRow() === 0) sheet.appendRow(HEADERS);
    // leading apostrophe: a name like "=SUM(...)" is stored as text, never run as a formula
    sheet.appendRow([new Date(), "'" + nombre, asistencia]);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err && err.message || err) };
  } finally {
    try { lock.releaseLock(); } catch (_) {}
  }
}

function health_() {
  try {
    const sheet = getSheet_();
    return { ok: true, msg: 'RSVP listo', hoja: sheet.getParent().getName(), pestaña: sheet.getName() };
  } catch (err) {
    return { ok: false, error: String(err && err.message || err) };
  }
}

function getSheet_() {
  let ss = null;
  if (SHEET_ID && SHEET_ID.indexOf('PEGA_AQUI') !== 0) ss = SpreadsheetApp.openById(SHEET_ID);
  else ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('No encuentro la hoja: pon su ID en SHEET_ID');
  const sheet = SHEET_NAME ? ss.getSheetByName(SHEET_NAME) : ss.getSheets()[0];
  if (!sheet) throw new Error('No existe la pestaña "' + SHEET_NAME + '"');
  return sheet;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
