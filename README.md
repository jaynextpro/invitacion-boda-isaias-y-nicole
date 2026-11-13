# Invitación digital — wedding landing page

A static site (HTML/CSS/JS, no framework, no build step to *run* it). Open
`index.html` through any static server, or upload the folder to any host.

```
index.html            generated from tools/template.html (don't hand-edit sections)
css/styles.css        all styling and animations
css/fonts.css         generated: the script font embedded as a data URI
js/config.js          ← the things you'll change: date, RSVP endpoint, map, song
js/main.js            intro, player, countdown, RSVP, scroll reveals
assets/img/           WebP images extracted from the Photoshop PDF (~1.2 MB total)
assets/audio/         put contigo.mp3 here
tools/build_assets.py regenerates assets/img + index.html from the PDF + design/
tools/photos.py       HD photo swaps (alignment, colour matching, frame fitting)
design/               client photos and the location-section design (build inputs)
deploy/               nginx snippet + upload script (see "Deploy on AWS Ubuntu with nginx")
tools/template.html   page skeleton used by the build
tools/fonts/          open-licence fonts with Times/Poppins metrics, used by the build to measure text
```

Local preview: `python3 -m http.server` in this folder → http://localhost:8000
Add `?abrir` to the URL to skip the envelope while you work.

## How the design became a page (and why)

Your PDF is a layered Photoshop export: every text/shape layer is stored as a
full-size image clipped to its outline (that's why it weighs 300 MB). The build
script uses that structure to:

* render the page **without** chosen layers → clean section backgrounds;
* render photos, buttons and colour swatches **alone** with transparency →
  separate elements that fade in on scroll;
* read every text line (text, font, size, baseline, angle, vertical stretch,
  colour) and write it as **real text** (SVG `<text>`), so it's sharp on every screen;
* paint out the static progress bar and countdown digits, which are now live HTML.

Fonts: Times New Roman (built into iPhone/Mac/Windows; Android gets Tinos, which
has identical metrics), Poppins (Google Fonts) and Verandah Reverie, served from
`css/fonts.css`, where the build embeds it as a data URI (some hosts, and the
Claude preview, only allow inline or Google fonts). It's your full font, losslessly
re-wrapped as WOFF2 (the font's metadata forbids subsetting). Its licence is
personal use; a commercial/web licence is available at mansgreback.com.

Why SVG text rather than plain HTML text: SVG places a line exactly on its baseline
in the design's own pixel coordinates. HTML text positions depend on each font's
internal line-box metrics, which differ slightly between fonts and platforms.

## 1. Add the song

Put the MP3 at `assets/audio/contigo.mp3` (or change `song` in `js/config.js`).
Keep it under ~5 MB: 128 kbps is plenty for a phone speaker.
`ffmpeg -i original.mp3 -b:a 128k -ac 2 assets/audio/contigo.mp3`

Browsers block autoplay. Tapping the envelope counts as a user gesture, so the
music starts there. The record spins only while the song is playing.

## 2. Collect RSVPs in a Google Sheet (free)

The page sends each answer to a small Google Apps Script, which appends a row
(`fecha | nombre | asistencia`) to your sheet. The script is in
`deploy/google-apps-script.gs`.

1. In the Google Sheet: **Extensions → Apps Script**. Replace everything with the
   contents of `deploy/google-apps-script.gs`.
2. Set `SHEET_ID` to the sheet's ID (the part of its URL between `/d/` and `/edit`).
   This makes the script work whether it was created from the sheet or on its own.
3. **Deploy → Manage deployments → ✏️ Edit** (or **New deployment** the first time):
   type **Web app**, *Execute as* **Me**, *Who has access* **Anyone**, *Version* **New version** → **Deploy**.
   Authorize when Google asks. That lets the script write to *your* sheet.
4. Copy the **/exec** URL into `rsvpEndpoint` in `js/config.js`.
   Editing the existing deployment keeps the same URL; a *New deployment* creates a new one.
5. **Test it**: open the /exec URL in a **private/incognito** window, which is how
   guests reach it (not logged in). It must show `{"ok":true,"msg":"RSVP listo",…}`.

How the page sends answers, and why: it loads the /exec URL as a `<script>`
(`?nombre=…&asistencia=…&callback=…`) instead of using `fetch()`. Browsers apply CORS
to `fetch()`, and Apps Script replies come through a redirect to another Google domain
that some browsers and devices block with "has been blocked by CORS policy", even when
the script is set up correctly. Script loads aren't subject to CORS. The Apps Script replies by
calling the page back with `{ok:true}` (saved) or `{ok:false,error:"…"}`, so the guest
only sees "¡Gracias!" when the row is really in the sheet; otherwise they get a retry
message and the console shows the reason (`[RSVP] …`).

**Troubleshooting (incognito test of the /exec URL):**

| you see | fix |
|---|---|
| a Google sign-in page | *Who has access* must be **Anyone** (not "Anyone with a Google account"). Work/school accounts may not offer it; use a personal Gmail account. |
| `{"ok":false,"error":"No encuentro la hoja…"}` | put the sheet ID in `SHEET_ID`, deploy a **new version** |
| `{"ok":false,"error":"…openById…"}` | wrong ID, or the deploying account can't open that sheet |
| "Script function not found: doGet" / old behaviour | code saved but not deployed: Manage deployments → Edit → **New version** |
| 404 / "unable to open the file" | wrong or archived deployment URL; copy the /exec URL again |
| `{"ok":true,…}` but the page still fails | `rsvpEndpoint` in `js/config.js` doesn't match that URL (re-deploy the site) |

Until an endpoint is set, answers are only saved in the guest's own browser
(demo mode). The form closes automatically after `rsvpDeadline`.

## 3. Other settings (js/config.js)

| key | what it does |
|---|---|
| `weddingDate` | Countdown target and the calendar event (3:30 p.m., from the location design). |
| `rsvpDeadline` | After this moment the form shows "El plazo… ha terminado". |
| `mapsUrl` | "Ver ubicación" button. Paste the share link of the exact pin. |
| `introDuration` | Envelope → couple photo → page, total ms from the tap (default 8650). Raising it lengthens time on the couple photo. Guests can tap the photo to skip. |

Player buttons: ♥ toggles a like, ⏮/⏭ seek ±10 s, ⊕ downloads the song
(`songDownloadName` sets the file name), and the bar is draggable.

When a guest accepts, the calendar event (`boda.ics`) downloads immediately. It
starts on the tap itself because phones block downloads that begin after waiting
for the network. The thank-you message also offers "Agregar al calendario" and a
Google Calendar link, in case the guest dismissed the first one.

## 4. Deploy on AWS Ubuntu with nginx

Live URL: `https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole/`

The site is static: nginx just serves files, so nothing (Node, Python…) runs on
the server. Only `index.html`, `css/`, `js/` and `assets/` are uploaded (~4.6 MB).
`tools/`, `design/` (36 MB of sources) and `deploy/` stay on your computer.

**Folder layout on the server mirrors the URL**, which keeps nginx simple:

```
/var/www/hsoul-ink/                                   ← root of hsoul.ink
└── live-projects/letters/invitacion-boda-isaias-y-nicole/
    ├── index.html   css/   js/   assets/
```

### 4.1 One-time: server basics (skip what you already have)

1. **AWS security group**: allow inbound TCP 80 and 443 from anywhere, and 22 from your IP.
2. **Elastic IP** on the instance, so its address survives stop/start, and a DNS
   **A record** `hsoul.ink` (and `www`) pointing to it.
3. On the server:
   ```bash
   sudo apt update && sudo apt install -y nginx rsync
   sudo ufw allow 'Nginx Full'        # only if ufw is enabled (sudo ufw status)
   ```
   rsync must exist on both machines; the upload script uses it.

### 4.2 Upload the site

From the project folder on your computer (macOS/Linux, or WSL on Windows):

```bash
deploy/deploy.sh ubuntu@hsoul.ink
# with a .pem key from AWS:
SSH_KEY=~/.ssh/aws.pem deploy/deploy.sh ubuntu@hsoul.ink
```

What it does: it creates the folder above once (owned by your login user, which
nginx only needs to read), then rsyncs the four web items. Files get standard
permissions (folders 755, files 644). Re-running it is how you update: only
changed files travel, and files deleted locally are deleted on the server.

### 4.3 nginx

Copy the snippet to the server:

```bash
scp deploy/nginx-invitacion.conf ubuntu@hsoul.ink:/tmp/
ssh ubuntu@hsoul.ink 'sudo mv /tmp/nginx-invitacion.conf /etc/nginx/snippets/invitacion-boda.conf'
```

Then include it **inside** the `server { }` block of hsoul.ink (usually
`/etc/nginx/sites-available/hsoul-ink` or `default`):

```nginx
server {
    server_name hsoul.ink www.hsoul.ink;
    root /var/www/hsoul-ink;
    # … what you already have …

    include snippets/invitacion-boda.conf;
}
```

No server block for hsoul.ink yet? Create `/etc/nginx/sites-available/hsoul-ink`
with the block above plus `listen 80; listen [::]:80;`, then
`sudo ln -s /etc/nginx/sites-available/hsoul-ink /etc/nginx/sites-enabled/` and
`sudo rm /etc/nginx/sites-enabled/default`.

Apply. Testing first means a typo never takes the running site down:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

What the snippet does, and why:

| rule | why |
|---|---|
| `…isaias-y-nicole` → 301 → `…isaias-y-nicole/` | the page uses relative links (`css/…`, `assets/…`); without the final `/` the browser would look for them one folder up and the page would load unstyled |
| `root /var/www/hsoul-ink` + `try_files` | serve the files; anything missing is a clean 404 |
| gzip for CSS/JS | `css/fonts.css` holds the embedded script font: 64 KB → 48 KB |
| HTML/CSS/JS `Cache-Control: no-cache` | file names don't change between updates, so browsers revalidate (a cheap 304) and guests always get the latest version |
| images/song cached 1 day | they rarely change; after replacing one, guests see it within a day (or on a hard refresh) |
| `deny` for `tools/`, `design/`, `deploy/`, dotfiles | in case they're ever uploaded by mistake |

The song supports seeking out of the box: nginx answers byte-range requests for static files.

### 4.4 HTTPS (free, auto-renewing)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d hsoul.ink -d www.hsoul.ink
```

Certbot adds the 443 server and the http→https redirect to your config and renews the
certificate automatically. You need HTTPS: WhatsApp/Facebook previews,
the RSVP request to Google and the "add to calendar" download all expect a secure page.

### 4.5 Check it

```bash
curl -I https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole     # 301 → …/
curl -I https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole/    # 200, text/html
curl -I https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole/assets/img/og.jpg   # 200
```

Then open the URL on a phone, and paste it into Facebook's Sharing Debugger
(developers.facebook.com/tools/debug) to see the link preview. WhatsApp caches a
preview the first time a link is shared, so check it before sending it to guests.

### 4.6 Using a different URL or folder

The path appears in three places. Change all three together:

1. `SITE_URL` in `tools/build_assets.py` (link previews), then rebuild. Without a
   rebuild, patch the built page directly:
   `sed -i 's#https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole/#https://NEW-URL/#g' index.html`
2. The two `location` paths in `deploy/nginx-invitacion.conf` (plus `root` if the folder moves).
3. `REMOTE_DIR` in `deploy/deploy.sh` (or run `REMOTE_DIR=/new/path deploy/deploy.sh …`).

Nothing else depends on the path: all links inside the page are relative.

### 4.7 Troubleshooting

| symptom | cause / fix |
|---|---|
| page shows unstyled / images missing | opened without the final `/` and the redirect isn't active: the snippet isn't included in the right `server` block, or nginx wasn't reloaded |
| 404 | files aren't at `/var/www/hsoul-ink/live-projects/letters/invitacion-boda-isaias-y-nicole/index.html`, or `root` differs |
| 403 | permissions (re-run deploy.sh) or the URL hits a denied folder |
| your site-wide security headers vanished on this page | nginx drops inherited `add_header` lines inside a location that sets its own: copy them into the snippet's locations |
| old version still showing | images are cached for a day: hard refresh, or rename the file |

## 5. Photos and the location section (design/ folder)

| file | where it goes | how |
|---|---|---|
| `portada_desvanecer.png` | couple in the lace oval (intro) | sharper copy of the design's photo: aligned feature-by-feature, the design's colour grading re-applied |
| `ft_antes_de_confirmacion.png` | photo before the RSVP | same |
| `conteo.png` | countdown background | same; the flowers drawn over it are kept from the design |
| `cuadro_dorado.png` | gold frame (ceremony card) | new photo, fitted into the frame's window in its perspective; frame ornaments and leaves stay on top |
| `ubicacion_diseno.png` | location section | background kept, text rebuilt as live text, button opens the photo modal |
| `ubi_casa.png` | photo in the location modal | cropped (`UBI["photo_crop"]`) to remove the car mirror |

To replace a photo, overwrite the file with the same name and rebuild. To change the
location texts, edit `UBI["lines"]` in `tools/build_assets.py` (and the design PNG).

## 6. Changing the design

Edit the PSD and export the PDF the same way, keeping the layer order. Then:

```
pip install pikepdf pypdfium2 pillow numpy fonttools brotli opencv-python-headless
python3 tools/build_assets.py path/to/invitacion_digital.pdf
```

If you add or remove layers, the layer indices in `OVERLAYS` shift.
`python3 tools/build_assets.py file.pdf --list` prints the count. The script
comments explain the mapping. Positions of player controls, form fields and
countdown digits are constants near the top of the script.
