#!/usr/bin/env python3
"""
Build the web assets for the wedding invitation from the layered Photoshop PDF.

How it works
------------
Photoshop exports a layered PDF where every text / vector-shape layer is a
full-canvas image clipped to that layer's outline. That lets us:
  * render the page WITHOUT chosen layers         -> clean section backgrounds
  * render ONE layer alone (transparent)          -> an element we can animate
  * read the text of Times / Poppins layers       -> real HTML text, placed at the
    exact baseline, size, angle and colour of the design (sharp on every screen)
The script titles use Verandah Reverie, embedded in css/fonts.css (the full font,
re-wrapped as WOFF2: its metadata forbids subsetting).

Usage
-----
    pip install pikepdf pypdfium2 pillow numpy fonttools brotli opencv-python-headless
    python3 tools/build_assets.py path/to/invitacion_digital.pdf

Outputs: assets/img/*.webp, tools/layout.json, index.html (from tools/template.html)

If you edit the design (e.g. fix a typo) re-export the PDF with the SAME layer
order and run this again. Layer indices below are the order layers are drawn in
the PDF; run with --list to print them with the font each one uses.
"""
import io, json, sys, html, math, pathlib, ctypes
import numpy as np
import pikepdf
import pypdfium2 as pdfium
import pypdfium2.raw as pdfraw
from PIL import Image, ImageDraw, ImageFilter, ImageFont
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import photos                      # tools/photos.py: HD photo swaps

Image.MAX_IMAGE_PIXELS = None      # the 2x render is 2160 x 29218

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / "assets" / "img"
FONTS = ROOT / "tools" / "fonts"   # metric-compatible fonts, used only to measure text
WIDTH = 1080                       # render width in px (2x for a 540px column)

# ---- Screens inside the single tall artboard (1080-wide coordinates) -------
ENVELOPE = (0, 1493)
PARTNERS = (1592, 3201)
MAIN_SECTIONS = [                  # (id, top, bottom)
    ("player",   3438, 4020),
    ("saludo",   4020, 6228),
    ("ceremonia",6228, 8240),
    ("ubicacion",8240, 9724),
    ("nota",     9724, 11128),
    ("foto",    11128, 11836),
    ("rsvp",    11836, 13236),
    ("cuenta",  13236, 14609),
]

# ---- Layer groups pulled out of the background (indices = draw order) -----
# kind: reveal = fade-up, fade = opacity only (sits on top of a matching bg),
#       pop = scale-in, plain = no animation, form = RSVP part, button-map = link
OVERLAYS = [
    ("env_text",      [1],            "intro"),
    ("partners_text", [4, 5],         "intro"),
    ("player_titulo", [14, 15],       "plain"),
    ("saludo_titulo", [9],            "reveal"),
    ("saludo_texto",  [7],            "reveal"),
    ("saludo_cierre", [8],            "reveal"),
    ("cer_foto",      [25],           "fade"),
    ("cer_l1",        [17],           "reveal"),
    ("cer_titulo",    [19],           "reveal"),
    ("cer_texto",     [18],           "reveal"),
    ("nota_titulo",   [29],           "reveal"),
    ("nota_texto",    [30],           "reveal"),
    ("color_1",       [31, 32, 37, 38, 39, 40], "pop"),
    ("color_2",       [36, 41, 42],   "pop"),
    ("color_3",       [33, 34, 43],   "pop"),
    ("color_4",       [35, 44],       "pop"),
    ("regalo_titulo", [45],           "reveal"),
    ("regalo_sub",    [46],           "reveal"),
    ("regalo_texto",  [47],           "reveal"),
    ("rsvp_titulo",   [51],           "reveal"),
    ("rsvp_texto",    [52, 53, 54, 55, 56, 57, 58], "reveal"),
    ("rsvp_label",    [59],           "form"),
    ("rsvp_linea",    [49, 50],       "form"),
    ("rsvp_pregunta", [60],           "form"),
    ("rsvp_si",       [61],           "form"),
    ("rsvp_no",       [62],           "form"),
    ("rsvp_radio_si", [63, 64],       "form"),
    ("rsvp_radio_no", [65, 66],       "form"),
    ("rsvp_boton",    [67, 68, 69],   "form"),
    ("cd_titulo",     [80],           "reveal"),
    ("cd_labels",     [82, 83, 84, 85], "reveal"),
]
REMOVED = [81]   # countdown digits -> live HTML

# Text that Photoshop exported as outlines (no text data in the PDF):
# (layers, text, css classes). Size/position are fitted to the outline's ink.
OUTLINED = [
    ([52, 53], "Para preparar cada detalle de nuestra celebración y garantizar", ""),
    ([54, 55], "la comodidad de todos nuestros invitados, te pedimos completar", ""),
    ([56, 57], "nuestro formulario de confirmación antes del", ""),
    ([58],     "15 de diciembre de 2026.", "i b u"),
]

# Alt text for elements that stay images
ALT = {
    "env_text": "Presiona el sobre para abrirlo.",
    "partners_text": "Mr. & Mrs. And so the adventure begins.",
    "saludo_titulo": "¡Querida familia y amigos!",
    "cer_foto": "Foto de la pareja en la playa",
    "cer_titulo": "Boda Civil",
    "nota_titulo": "Nota especial",
    "color_1": "Blanco", "color_2": "Rojo", "color_3": "Beige", "color_4": "Verde olivo",
    "regalo_titulo": "Sugerencia",
    "rsvp_titulo": "Confirmación",
    "cd_titulo": "Nuestro para siempre empieza en…",
}

# ---- Where the site lives (used for link previews: WhatsApp, Facebook…) ----
# Must end with "/". Changing it later without a rebuild: see README → Deploy.
SITE_URL = "https://hsoul.ink/live-projects/letters/invitacion-boda-isaias-y-nicole/"

# ---- Client photos (design/ folder) -----------------------------------------
DESIGN = ROOT / "design"
HI = 2                              # backgrounds are rendered at 2x (2160 px wide)
EXPORT = {"foto": 1.5, "cuenta": 1.5}   # photo sections exported at 1620 px, others 1080
# Sharper copies of photos already in the design: aligned + colour-matched in place.
#   (file, where): where = ("layer", n) for a photo layer, or ("section", id)
HD_PHOTOS = [
    ("portada_desvanecer.png",       ("layer", 3)),        # couple in the lace oval (intro)
    ("ft_antes_de_confirmacion.png", ("section", "foto")), # photo before the RSVP
    ("conteo.png",                   ("section", "cuenta")),
]
# A new photo for the gold frame (ceremony card): (overlay name, file, focus x/y)
FRAME_PHOTO = ("cer_foto", "cuadro_dorado.png", (0.5, 0.42))

# Location section, rebuilt from design/ubicacion_diseno.png with live text.
# Lines top to bottom: (text, family t=Times / v=Verandah, extra classes[, text as drawn in
# the design file]). The last item lets the page say something different from the PNG
# (e.g. a corrected name): size and position are measured on the design's text.
UBI = dict(
    design="ubicacion_diseno.png",
    lines=[
        ("El evento se llevará a cabo en:", "t", ""),
        ("El Jardín Casa Rosada", "v", "", "El Jardín Casa Rosasa"),
        ("en casa de la Sra. Doris Campos.", "t", ""),
        ("A las 3:30 p.m.", "t", "u"),
        ("Residencial Riverside, San Miguel", "t", ""),
    ],
    button="Ver ubicación",
    photo="ubi_casa.png",           # shown in the "Ver ubicación" modal
    photo_crop=(0, 300, 2400, 2500),  # x0, y0, x1, y1 in the original: drops the car mirror at the bottom
)

# ---- Hand-measured geometry of interactive bits (1080-wide coordinates) ---
DISC = dict(cx=267.5, cy=3714, r=161)          # vinyl record, spins
SEAL = dict(cx=538, cy=731, r=172)             # wax seal on the envelope
PROGRESS_ERASE = (455, 3804, 906, 3844)        # baked progress bar -> painted out

# ---- Fonts used to measure text (metric-compatible with the design fonts) --
FONT_FILES = {
    ("t", False, 400): "LiberationSerif-Regular.ttf",   # = Times New Roman metrics
    ("t", True, 400):  "LiberationSerif-Italic.ttf",
    ("t", False, 700): "LiberationSerif-Bold.ttf",
    ("t", True, 700):  "LiberationSerif-BoldItalic.ttf",
    ("v", False, 400): "VerandahReverie.otf",          # the design's script font
    ("p", False, 500): "Poppins-Medium.ttf",
    ("p", False, 700): "Poppins-Bold.ttf",
}
_fcache = {}
def mfont(fam, ital, wt):
    key = (fam, ital, wt)
    if key not in _fcache:
        _fcache[key] = ImageFont.truetype(str(FONTS / FONT_FILES[key]), 1000)
    return _fcache[key]


def load_ops(src):
    pdf = pikepdf.open(src)
    page = pdf.pages[0]
    ops = list(pikepdf.parse_content_stream(page))
    fm = {str(k): str(v.BaseFont) for k, v in page.Resources.Font.items()}
    layer_fonts, cur = [], set()
    for operands, op in ops:
        if str(op) == "Tf": cur.add(fm[str(operands[0])].split("+")[-1])
        if str(op) == "Do": layer_fonts.append(cur); cur = set()
    return pdf, ops, layer_fonts


def content_for(ops, keep):
    out, k = [], -1
    for operands, op in ops:
        if str(op) == "Do":
            k += 1
            if k not in keep:
                continue
        out.append((operands, op))
    return pikepdf.unparse_content_stream(out)


def is_live_font(name):
    return name.startswith(("TimesNewRoman", "Poppins", "VerandahReverie"))


# --------------------------------------------------------------------------
# Text extraction: characters -> lines with baseline, size, angle, spacing
# --------------------------------------------------------------------------
def extract_lines(textpage, ph, scale):
    n = textpage.count_chars()
    buf = ctypes.create_string_buffer(256); flags = ctypes.c_int()
    m = pdfraw.FS_MATRIX(); ox = ctypes.c_double(); oy = ctypes.c_double()
    chars = []
    for i in range(n):
        u = chr(pdfraw.FPDFText_GetUnicode(textpage, i))
        if not u.strip(): continue
        pdfraw.FPDFText_GetFontInfo(textpage, i, buf, 256, ctypes.byref(flags))
        name = buf.value.decode(errors="ignore").split("+")[-1]
        if not is_live_font(name): continue
        fam = "p" if name.startswith("Poppins") else ("v" if name.startswith("Verandah") else "t")
        ital = "Italic" in name
        wt = 700 if "Bold" in name else (500 if "Medium" in name else 400)
        pdfraw.FPDFText_GetMatrix(textpage, i, ctypes.byref(m))
        pdfraw.FPDFText_GetCharOrigin(textpage, i, ctypes.byref(ox), ctypes.byref(oy))
        size = math.hypot(m.a, m.b); th = math.atan2(m.b, m.a)
        x, y = ox.value, oy.value                              # pt, y-up
        uu = x*math.cos(th) + y*math.sin(th); vv = -x*math.sin(th) + y*math.cos(th)
        ky = math.hypot(m.c, m.d) / size if size else 1.0      # Photoshop vertical scale
        chars.append(dict(u=u, fam=fam, ital=ital, wt=wt, size=size, th=th, uu=uu, vv=vv, ky=ky))

    # a line that exists in two overlapping layers yields every glyph twice: drop repeats
    uniq, seen_c = [], set()
    for c in chars:
        k = (c["u"], c["fam"], round(c["uu"], 1), round(c["vv"], 1))
        if k not in seen_c: seen_c.add(k); uniq.append(c)
    chars = uniq

    # cluster into lines
    groups = {}
    for c in chars:
        key = (c["fam"], c["ital"], c["wt"], round(c["size"], 1), round(math.degrees(c["th"]) * 2) / 2)
        groups.setdefault(key, []).append(c)
    lines = []
    for key, cs in groups.items():
        cs.sort(key=lambda c: (-c["vv"], c["uu"]))
        cur = []
        for c in cs:
            if cur and abs(c["vv"] - cur[0]["vv"]) > 0.3 * c["size"]:
                lines.append((key, cur)); cur = []
            cur.append(c)
        if cur: lines.append((key, cur))

    # split a "line" where words are far apart (e.g. Días · Horas · Minutos · Segundos)
    split = []
    for key, cs in lines:
        cs.sort(key=lambda c: c["uu"])
        f = mfont(key[0], key[1], key[2]); cur = [cs[0]]
        for a, b in zip(cs, cs[1:]):
            if abs(b["uu"] - a["uu"]) > 0.02 * a["size"] and \
               b["uu"] - (a["uu"] + f.getlength(a["u"]) / 1000 * a["size"]) > 1.0 * a["size"]:
                split.append((key, cur)); cur = []
            cur.append(b)
        split.append((key, cur))

    out, seen = [], set()
    for (fam, ital, wt, _, _), cs in split:
        f = mfont(fam, ital, wt); size = cs[0]["size"]; th = cs[0]["th"]
        adv = lambda ch: f.getlength(ch) / 1000 * size
        # characters sharing one origin are a ligature glyph (e.g. "fi"): one cluster
        clusters = []
        for c in cs:
            if clusters and abs(c["uu"] - clusters[-1][0]) < 0.02 * size:
                clusters[-1][1] += c["u"]
            else:
                clusters.append([c["uu"], c["u"]])
        text = clusters[0][1]
        for (ua, ta), (ub, tb) in zip(clusters, clusters[1:]):
            if ub - (ua + adv(ta)) > 0.12 * size: text += " "
            text += tb
        u0 = clusters[0][0]; u1 = clusters[-1][0] + adv(clusters[-1][1])
        natural = f.getlength(text) / 1000 * size
        ls = (u1 - u0 - natural) / max(1, len(text) - 1)
        vb = sum(c["vv"] for c in cs) / len(cs); uc = (u0 + u1) / 2
        x = uc*math.cos(th) - vb*math.sin(th); y = uc*math.sin(th) + vb*math.cos(th)
        X, Y = x * scale, (ph - y) * scale
        if fam == "t" and size * scale > 80 and all(ch in "0123456789: " for ch in text):
            continue                                   # countdown digits are live HTML
        key = (text, round(X / 4), round(Y / 4))
        if key in seen: continue                       # same line in two layers
        seen.add(key)
        cls = {"t": "", "p": "p", "v": "v"}[fam] + (" i" if ital else "") + (" b" if wt == 700 else "") + (" m" if wt == 500 else "")
        ky = sorted(c["ky"] for c in cs)[len(cs) // 2]
        out.append(dict(text=text, X=X, Y=Y, fs=size*scale, ls=ls*scale, ky=ky,
                        rot=-math.degrees(th), cls=cls.strip(), w=(u1-u0)*scale))
    return out


def fit_outlined(alpha_img, text, classes, ref=None):
    """Fit Times text to an outlined line's ink: returns line dict in 1080 coords."""
    a = np.asarray(alpha_img)
    ys, xs = np.nonzero(a > 40)
    l, t, r, b = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    ital, bold = "i" in classes.split(), "b" in classes.split()
    f = mfont("t", ital, 700 if bold else 400)
    x0, y0, x1, y1 = f.getbbox(text, anchor="ls")
    if ref is None:
        fs = 1000 * (b - t) / (y1 - y0)
        base = b - y1 * fs / 1000
    else:                                    # underlined line: size from siblings, baseline from ink top
        fs = ref
        base = t - y0 * fs / 1000
    natural_ink = (x1 - x0) * fs / 1000
    ls = ((r - l) - natural_ink) / max(1, len(text) - 1)
    adv = f.getlength(text) / 1000 * fs
    ink_c = (x0 + x1) / 2 * fs / 1000
    X = (l + r) / 2 + (adv / 2 - ink_c)
    return dict(text=text, X=X, Y=base, fs=fs, ls=ls, ky=1.0, rot=0.0, cls=classes, w=r - l)


def main(src):
    IMG.mkdir(parents=True, exist_ok=True)
    pdf, ops, layer_fonts = load_ops(src)
    n = len(layer_fonts)
    if "--list" in sys.argv:
        for i, fset in enumerate(layer_fonts): print(i, sorted(fset) or "-")
        return
    text_layers = {i for i, fs in enumerate(layer_fonts) if fs and all(is_live_font(f) for f in fs)}
    text_layers |= {l for layers, _, _ in OUTLINED for l in layers}

    pulled = {i for _, idx, _ in OVERLAYS for i in idx} | set(REMOVED)
    variants = [("bg", set(range(n)) - pulled)]
    for name, idx, _ in OVERLAYS:
        variants.append((name + ":img", set(idx) - text_layers))
        variants.append((name + ":txt", set(idx) & text_layers))
    for k, (layers, _, _) in enumerate(OUTLINED):
        variants.append((f"outl{k}", set(layers)))
    for f, (kind, ref) in HD_PHOTOS:
        if kind == "layer": variants.append((f"photo{ref}", {ref}))
    page_of = {}
    base = pdf.pages[0]
    for vname, keep in variants:
        pdf.pages.append(base)
        pdf.pages[-1].obj.Contents = pdf.make_stream(content_for(ops, keep))
        page_of[vname] = len(pdf.pages) - 1
    buf = io.BytesIO(); pdf.save(buf)
    doc = pdfium.PdfDocument(buf.getvalue())
    pw, ph = doc[0].get_size(); scale = WIDTH / pw

    def render(vname, transparent=False, k=1):
        fill = (255, 255, 255, 0) if transparent else (255, 255, 255, 255)
        return doc[page_of[vname]].render(scale=scale * k, fill_color=fill).to_pil()

    save = lambda im, name, q=82: im.save(IMG / f"{name}.webp", "WEBP", quality=q, method=6)
    for old in IMG.glob("el_*.webp"): old.unlink()

    # ---------- backgrounds (2x) ----------
    bg = render("bg", k=HI).convert("RGB")
    ImageDraw.Draw(bg).rectangle([v * HI for v in PROGRESS_ERASE], fill=(255, 255, 255))
    bga = np.array(bg)
    for fname, (kind, ref) in HD_PHOTOS:
        new = np.asarray(Image.open(DESIGN / fname).convert("RGB"))
        if kind == "layer":
            lay = render(f"photo{ref}", transparent=True, k=HI)
            x0, y0, x1, y1 = lay.getchannel("A").getbbox()
            mask = np.asarray(lay.getchannel("A").crop((x0, y0, x1, y1))).astype(np.float32) / 255
        else:
            _, t, b = next(sct for sct in MAIN_SECTIONS if sct[0] == ref)
            x0, y0, x1, y1 = 0, t * HI, WIDTH * HI, b * HI
            mask = None
        out, st = photos.hd_swap(bga[y0:y1, x0:x1], new, mask)
        print(f"  HD photo {fname}: {st}")
        bga[y0:y1, x0:x1] = out
    bg = Image.fromarray(bga)

    def export(box1080, name, k=1.0, q=82):
        l, t, r, b = box1080
        im = bg.crop((l * HI, t * HI, r * HI, b * HI))
        if k != HI:
            im = im.resize((round((r - l) * k), round((b - t) * k)), Image.LANCZOS)
        save(im, name, q)
    # link-preview image (1200x630 JPEG: WhatsApp/Facebook handle JPEG best)
    ft = next(sct for sct in MAIN_SECTIONS if sct[0] == "foto")
    og = bg.crop((0, ft[1] * HI, WIDTH * HI, ft[2] * HI))
    ch = round(og.width * 630 / 1200); oy = (og.height - ch) // 2
    og.crop((0, oy, og.width, oy + ch)).resize((1200, 630), Image.LANCZOS).save(
        IMG / "og.jpg", "JPEG", quality=85, optimize=True, progressive=True)
    export((0, ENVELOPE[0], WIDTH, ENVELOPE[1]), "intro_sobre", k=2, q=84)
    export((0, PARTNERS[0], WIDTH, PARTNERS[1]), "intro_pareja", k=2, q=84)
    for sid, top, bottom in MAIN_SECTIONS:
        if sid == "ubicacion": continue            # rebuilt from its own design file
        export((0, top, WIDTH, bottom), f"sec_{sid}", k=EXPORT.get(sid, 1.0))

    def circle_crop(c, name, feather=1.2, gold_only=False):
        c = {k: v * HI for k, v in c.items()}                  # work on the 2x render
        x0, y0 = c["cx"] - c["r"], c["cy"] - c["r"]; size = int(2 * c["r"]) + 2
        crop = bg.crop((int(x0), int(y0), int(x0) + size, int(y0) + size)).convert("RGBA")
        ss = 4; m = Image.new("L", (size*ss, size*ss), 0)
        ImageDraw.Draw(m).ellipse((0, 0, (2*c["r"])*ss, (2*c["r"])*ss), fill=255)
        m = m.resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(feather))
        if gold_only:
            # keep only the wax: trace its outer edge angle by angle (it is star-shaped
            # from its centre) so pale highlights on the rim don't punch holes in the mask
            arr = np.asarray(crop.convert("RGB")).astype(np.int16)
            sat = arr[:, :, 0] - arr[:, :, 2]
            g = Image.fromarray(np.clip((sat - 55) * 8, 0, 255).astype(np.uint8))
            ga = np.asarray(g) > 128; cc = c["r"]; rad = []
            angles = np.linspace(0, 2*np.pi, 720, endpoint=False)
            for t in angles:
                rr = np.arange(0, int(c["r"]) - 1)
                xs_ = (cc + rr*np.cos(t)).astype(int); ys_ = (cc + rr*np.sin(t)).astype(int)
                on = np.nonzero(ga[ys_, xs_])[0]; rad.append(on.max() if len(on) else 0)
            rad = np.array(rad, float); k = 9
            pad_ = np.concatenate([rad[-k:], rad, rad[:k]])
            rad = np.array([np.percentile(pad_[i:i+2*k+1], 70) for i in range(len(rad))])
            poly = Image.new("L", (size*ss, size*ss), 0)
            pts = [((cc + (r_+0.5)*np.cos(t))*ss, (cc + (r_+0.5)*np.sin(t))*ss) for t, r_ in zip(angles, rad)]
            ImageDraw.Draw(poly).polygon(pts, fill=255)
            m = poly.resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.6))
        crop.putalpha(m); save(crop, name, 90)
    circle_crop(DISC, "disco", 1.2)
    circle_crop(SEAL, "sello", 2.0, gold_only=True)
    # browser tab icon + iPhone home-screen icon from the gold seal
    seal = Image.open(IMG / "sello.webp").convert("RGBA"); seal = seal.crop(seal.getchannel("A").getbbox())
    side = max(seal.size); sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(seal, ((side - seal.width) // 2, (side - seal.height) // 2))
    sq.resize((48, 48), Image.LANCZOS).save(IMG / "favicon.png")
    touch = Image.new("RGB", (180, 180), (243, 240, 232)); s150 = sq.resize((150, 150), Image.LANCZOS)
    touch.paste(s150, (15, 15), s150); touch.save(IMG / "apple-touch-icon.png")

    # ---------- live text ----------
    lines = extract_lines(doc[0].get_textpage(), ph, scale)
    outl = []
    for k, (layers, text, cls) in enumerate(OUTLINED):
        alpha = render(f"outl{k}", transparent=True).getchannel("A")
        ref = None if "u" not in cls.split() else sum(o["fs"] for o in outl) / max(1, len(outl))
        outl.append(fit_outlined(alpha, text, cls, ref))
    lines += outl
    ubi_sec = next(sct for sct in MAIN_SECTIONS if sct[0] == "ubicacion")
    lines = [L for L in lines if not (ubi_sec[1] <= L["Y"] < ubi_sec[2])]   # section rebuilt

    # ---------- overlays ----------
    def alpha_box(im, pad=3):
        a = np.asarray(im.getchannel("A")); ys, xs = np.nonzero(a > 3)
        if len(xs) == 0: return None
        return [max(0, xs.min()-pad), max(0, ys.min()-pad), min(WIDTH, xs.max()+1+pad), min(im.height, ys.max()+1+pad)]

    meta, used = {}, set()
    for name, idx, kind in OVERLAYS:
        img_l, txt_l = set(idx) - text_layers, set(idx) & text_layers
        im_img = render(name + ":img", True) if img_l else None
        im_txt = render(name + ":txt", True) if txt_l else None
        boxes = [b for b in (alpha_box(im_img) if im_img else None, alpha_box(im_txt) if im_txt else None) if b]
        box = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        entry = dict(box=[int(v) for v in box], kind=kind, alt=ALT.get(name, ""), image=bool(img_l), lines=[])
        if img_l and FRAME_PHOTO and name == FRAME_PHOTO[0]:
            hb = [v * HI for v in box]
            lay = np.asarray(render(name + ":img", True, k=HI).crop(hb))
            new = np.asarray(Image.open(DESIGN / FRAME_PHOTO[1]).convert("RGB"))
            out, st = photos.window_fill(lay, bga[hb[1]:hb[3], hb[0]:hb[2]], new, focus=FRAME_PHOTO[2])
            print(f"  frame photo {FRAME_PHOTO[1]}: {st}")
            save(Image.fromarray(out, "RGBA"), f"el_{name}", 88)
        elif img_l:
            save(im_img.crop(box), f"el_{name}", 90)
        if txt_l:
            arr = np.asarray(im_txt)
            for li, L in enumerate(lines):
                if li in used: continue
                if box[0]-4 <= L["X"] <= box[2]+4 and box[1]-4 <= L["Y"] <= box[3]+4:
                    used.add(li)
                    # colour: median of fully-opaque text pixels on this line
                    y0 = int(max(0, L["Y"] - 0.7*L["fs"])); y1 = int(L["Y"] + 2)
                    x0 = int(max(0, L["X"] - L["w"]/2)); x1 = int(min(WIDTH, L["X"] + L["w"]/2))
                    reg = arr[y0:y1, x0:x1].reshape(-1, 4); reg = reg[reg[:, 3] > 250]
                    rgb = np.median(reg[:, :3], axis=0).astype(int) if len(reg) else np.array([255, 255, 255])
                    if rgb.min() >= 238: rgb = np.array([255, 255, 255])   # JPEG noise on white
                    entry["lines"].append(dict(L, color="#%02x%02x%02x" % tuple(rgb)))
        meta[name] = entry
    missing = [L["text"] for i, L in enumerate(lines) if i not in used]
    if missing: print("WARNING: text lines not placed:", missing)
    write_font_css()
    meta["_ubicacion"] = build_ubicacion(save)
    (ROOT / "tools" / "layout.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=float))
    write_html(meta)
    print("done:", len(list(IMG.glob('*.webp'))), "images,", len(used), "text lines")


def fit_ink(ink, text, fam, classes, ref_fs=None, by_width=False):
    """Fit one line of text to its ink in a flat design image.
    ink: bool mask (full image coords) of this line's pixels. Size comes from the
    ink height (or ref_fs), the baseline from the ink bottom (or top when the line
    is underlined), letter-spacing from the ink width."""
    ys, xs = np.nonzero(ink); l, t, r, b = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    cls = classes.split()
    f = mfont(fam, "i" in cls, 700 if "b" in cls else 400)
    x0, y0, x1, y1 = f.getbbox(text, anchor="ls")
    if by_width:      # underlined line: the underline clips descenders, so size by width, align by top
        fs = 1000 * (r - l) / (x1 - x0); base = t - y0 * fs / 1000
    else:
        fs = ref_fs or 1000 * (b - t) / (y1 - y0)
        base = (t - y0 * fs / 1000) if ref_fs else (b - y1 * fs / 1000)
    ls = ((r - l) - (x1 - x0) * fs / 1000) / max(1, len(text) - 1)
    adv = f.getlength(text) / 1000 * fs
    X = (l + r) / 2 + (adv / 2 - (x0 + x1) / 2 * fs / 1000)
    return dict(text=text, X=float(X), Y=float(base), fs=float(fs), ls=float(ls), ky=1.0, rot=0.0,
                cls=(("v " if fam == "v" else "") + classes).strip(), w=float(r - l))


def build_ubicacion(save):
    """Location section from design/ubicacion_diseno.png: the flat background is
    kept (text and button painted out), the text becomes live SVG text and the
    button a real <button> that opens the photo modal."""
    im = np.asarray(Image.open(DESIGN / UBI["design"]).convert("RGB")).astype(np.int16)
    H, W, _ = im.shape
    bgc = np.median(im[5:60, 20:W - 20].reshape(-1, 3), axis=0).astype(np.uint8)   # flat olive
    white = im.min(axis=2) > 170
    # button: the big white rounded rectangle
    rows = np.nonzero(white.sum(axis=1) > 0.5 * W)[0]
    by0, by1 = int(rows.min()), int(rows.max()) + 1
    cols = np.nonzero(white[(by0 + by1) // 2])[0]; bx0, bx1 = int(cols.min()), int(cols.max()) + 1
    radius = int(np.nonzero(white[by0])[0].min() - bx0)
    # text lines above the button: bands of white ink
    prof = white[:by0 - 10].sum(axis=1)
    bands, s0 = [], None
    for y, v in enumerate(prof):
        if v and s0 is None: s0 = y
        if not v and s0 is not None: bands.append((s0, y)); s0 = None
    bands = [bd for bd in bands if bd[1] - bd[0] > 8]
    if len(bands) != len(UBI["lines"]):
        raise RuntimeError(f"expected {len(UBI['lines'])} text lines in {UBI['design']}, found {len(bands)}")
    lines, ul = [], None
    plain_fs = []
    for (t, b), spec in zip(bands, UBI["lines"]):
        text, fam, cls = spec[:3]
        drawn = spec[3] if len(spec) > 3 else text
        ink = np.zeros_like(white); ink[t:b] = white[t:b]
        ref = None
        if "u" in cls.split():
            cov = ink.sum(axis=1)
            urows = np.nonzero(cov > 0.6 * np.ptp(np.nonzero(ink.any(axis=0))[0]))[0]
            ux = np.nonzero(ink[urows].any(axis=0))[0]
            ul = (float(ux.min()), float(urows.min()), float(ux.max() + 1), float(urows.max() + 1))
            ink[urows.min():urows.max() + 1] = False
            ink[urows.min() - 2:urows.max() + 3] = False
        L = fit_ink(ink, drawn, fam, cls, by_width="u" in cls.split())
        if drawn != text:      # same size/baseline/centre/spacing, new wording
            L["text"] = text
        if ul and "u" in cls.split(): L["ul"] = ul
        L["color"] = "#ffffff"
        lines.append(L)
    # button label: dark ink inside the button
    inner = np.zeros_like(white); pad = radius
    inner[by0 + 8:by1 - 8, bx0 + pad:bx1 - pad] = ~white[by0 + 8:by1 - 8, bx0 + pad:bx1 - pad]
    bl = fit_ink(inner, UBI["button"], "t", "")
    core = im[inner & (im.max(axis=2) < 200)]
    bl["color"] = "#%02x%02x%02x" % tuple(np.median(core, axis=0).astype(int)) if len(core) else "#687149"
    # button shape as an image (text painted out): like the RSVP button, which dark
    # modes leave alone, unlike a CSS background colour
    # drawn at 4x and downsampled: a clean anti-aliased white rounded rectangle with
    # the measured size and corner radius (saved at 2x for sharp phone screens)
    ss, k2 = 4, 2
    bw, bh = (bx1 - bx0) * k2, (by1 - by0) * k2
    shape = Image.new("L", (bw * ss, bh * ss), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, bw * ss - 1, bh * ss - 1), radius=radius * k2 * ss, fill=255)
    shape = shape.resize((bw, bh), Image.LANCZOS)
    btn_img = Image.new("RGBA", (bw, bh), (255, 255, 255, 0)); btn_img.putalpha(shape)
    save(btn_img, "el_ubi_boton", 92)
    # background without text and button
    clean = im.astype(np.uint8).copy()
    clean[bands[0][0] - 12:by1 + 12] = bgc
    save(Image.fromarray(clean), "sec_ubicacion", 86)
    # modal photo
    ph = Image.open(DESIGN / UBI["photo"]).convert("RGB").crop(UBI["photo_crop"])
    ph.thumbnail((1200, 1200), Image.LANCZOS)
    save(ph, "ubi_casa", 82)
    return dict(height=H, lines=lines, button=dict(box=[bx0, by0, bx1, by1], radius=radius, label=bl),
                bg="#%02x%02x%02x" % tuple(int(v) for v in bgc), photo_size=list(ph.size))


def ubicacion_html(u):
    h = u["height"]
    groups = [[0], [1], [2, 3, 4]]          # stagger: intro line, venue name, details
    items = []
    for gi, idxs in enumerate(groups):
        ls = [u["lines"][i] for i in idxs]
        l = min(L["X"] - L["w"] / 2 for L in ls) - 8; r = max(L["X"] + L["w"] / 2 for L in ls) + 8
        t = min(L["Y"] - L["fs"] for L in ls) - 6
        b = max(L.get("ul", (0, 0, 0, L["Y"] + 0.3 * L["fs"]))[3] for L in ls) + 6
        entry = dict(box=[l, t, r, b], lines=ls)
        items.append(f'<div class="el reveal" style="{place([l, t, r, b], 0, h)};--d:{gi}">{text_html(entry)}</div>')
    bx = u["button"]; bl = bx["label"]
    lab = text_html(dict(box=bx["box"], lines=[bl]))
    items.append(f'<button type="button" class="el reveal ubi-btn" id="ubiBtn" aria-haspopup="dialog" '
                 f'aria-controls="ubiModal" style="{place(bx["box"], 0, h)};--d:3;--rad:{bx["radius"]}">'
                 f'<img src="assets/img/el_ubi_boton.webp" alt="" loading="lazy" decoding="async">{lab}'
                 f'<span class="sr">{html.escape(bl["text"])}</span></button>')
    return (f'<section class="sec" id="ubicacion" style="aspect-ratio:{WIDTH}/{h}">\n'
            f'  <img class="bg" src="assets/img/sec_ubicacion.webp" alt="" width="{WIDTH}" height="{h}" loading="lazy" decoding="async">\n  '
            + "\n  ".join(items) + "\n</section>")


def modal_html(u):
    w, h = u["photo_size"]
    pin = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5'
           'a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>')
    return ('<dialog class="modal" id="ubiModal" aria-label="Ubicación del evento">\n'
            '  <div class="modal-card">\n'
            f'    <img class="modal-photo" data-src="assets/img/ubi_casa.webp" alt="Fachada de la casa donde será el evento" width="{w}" height="{h}">\n'
            '    <div class="modal-actions">\n'
            f'      <a class="mbtn primary" id="mapsLink" href="#" target="_blank" rel="noopener">{pin}Ver en Google Maps</a>\n'
            '      <button type="button" class="mbtn" id="ubiClose">Cerrar</button>\n'
            '    </div>\n  </div>\n</dialog>')


# Body text font. Times New Roman where a device really has it (iPhone, Mac, Windows);
# everywhere else Tinos, which has Times' exact character widths (OFL licence:
# tools/fonts/Tinos-LICENSE-OFL.txt). Why not just "font-family: Times New Roman":
# Android maps that name to its own serif (Noto Serif), which is wider and taller,
# so lines ran past the cards and frames on Samsung/Android phones.
SERIF_FACES = [   # (file, style, weight, local names of the real Times New Roman face)
    ("Tinos-Regular.ttf",    "normal", 400, ["Times New Roman", "TimesNewRomanPSMT"]),
    ("Tinos-Italic.ttf",     "italic", 400, ["Times New Roman Italic", "TimesNewRomanPS-ItalicMT"]),
    ("Tinos-BoldItalic.ttf", "italic", 700, ["Times New Roman Bold Italic", "TimesNewRomanPS-BoldItalicMT"]),
]
SERIF_CHARS = "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201E,U+2022,U+2026,U+20AC"


def write_font_css():
    """Embed the fonts in css/fonts.css as data: URIs.
    Why: some hosts (and the Claude preview) only allow fonts that are inlined or
    from Google Fonts; inlining also means they arrive with the CSS, never late.
    Verandah Reverie is kept whole (its metadata forbids subsetting), just WOFF2-compressed;
    Tinos is trimmed to Spanish/English characters (allowed by its licence)."""
    import base64
    from fontTools.ttLib import TTFont
    from fontTools import subset as fsub
    def woff2_b64(font):
        font.flavor = "woff2"; buf = io.BytesIO(); font.save(buf)
        return base64.b64encode(buf.getvalue()).decode()
    css = ["/* Generated by tools/build_assets.py from tools/fonts/ */"]
    css.append("@font-face {\n  font-family: \"Verandah Reverie\";\n"
               f"  src: url(data:font/woff2;base64,{woff2_b64(TTFont(str(FONTS / 'VerandahReverie.otf')))}) format(\"woff2\");\n"
               "  font-display: block;\n}")
    opts = fsub.Options(); opts.layout_features = ["kern", "liga"]; opts.name_IDs = ["*"]; opts.notdef_outline = True
    for fname, style, weight, local_names in SERIF_FACES:
        font = TTFont(str(FONTS / fname))
        sub = fsub.Subsetter(opts); sub.populate(unicodes=fsub.parse_unicodes(SERIF_CHARS)); sub.subset(font)
        locals_ = ", ".join(f'local("{n}")' for n in local_names)
        css.append("@font-face {\n  font-family: \"Invite Serif\";\n"
                   f"  font-style: {style};\n  font-weight: {weight};\n"
                   f"  src: {locals_},\n       url(data:font/woff2;base64,{woff2_b64(font)}) format(\"woff2\");\n"
                   "}")
    (ROOT / "css" / "fonts.css").write_text("\n".join(css) + "\n")


# --------------------------------------------------------------------------
def pct(v, total): return f"{v/total*100:.4f}%"

def place(box, top, h):
    l, t, r, b = box
    return (f"left:{pct(l, WIDTH)};top:{pct(t-top, h)};"
            f"width:{pct(r-l, WIDTH)};height:{pct(b-t, h)}")

def area(x0, y0, x1, y1, top, h): return place([x0, y0, x1, y1], top, h)

def text_html(entry, cls_name="tsvg", style=""):
    """Lines as SVG <text>: SVG places text exactly on its baseline (x,y) in the
    design's own pixel coordinates, independent of each font's line-box metrics,
    and the viewBox scales it with the page. Still real, sharp, selectable text."""
    if not entry["lines"]: return ""
    l, t, r, b = entry["box"]
    st = f' style="{style}"' if style else ""
    out = [f'<svg class="{cls_name}"{st} viewBox="{l} {t} {r-l} {b-t}" preserveAspectRatio="none">']
    for L in sorted(entry["lines"], key=lambda L: L["Y"]):
        cls = L["cls"].split()
        attrs = [f'x="{L["X"]:.2f}"', f'y="{L["Y"]:.2f}"', f'font-size="{L["fs"]:.2f}"', 'text-anchor="middle"',
                 f'fill="{L["color"]}"']
        if abs(L["ls"]) > 0.05: attrs.append(f'letter-spacing="{L["ls"]:.2f}"')
        tf = []
        if abs(L["rot"]) > 0.05: tf.append(f'rotate({L["rot"]:.2f} {L["X"]:.2f} {L["Y"]:.2f})')
        if abs(L.get("ky", 1) - 1) > 0.01:   # vertical stretch about the baseline point
            tf.append(f'translate({L["X"]:.2f} {L["Y"]:.2f}) scale(1 {L["ky"]:.4f}) translate({-L["X"]:.2f} {-L["Y"]:.2f})')
        if tf: attrs.append(f'transform="{" ".join(tf)}"')
        if "p" in cls: attrs.append('class="p"')
        if "v" in cls: attrs.append('class="v"')
        if "i" in cls: attrs.append('font-style="italic"')
        if "b" in cls: attrs.append('font-weight="700"')
        if "m" in cls: attrs.append('font-weight="500"')
        out.append(f'<text {" ".join(attrs)}>{html.escape(L["text"])}</text>')
        if "u" in cls:   # drawn underline: SVG text-decoration support is uneven across browsers
            if "ul" in L:     # measured from the design
                x0, y0, x1, y1 = L["ul"]
                out.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1-x0:.2f}" height="{y1-y0:.2f}" fill="{L["color"]}"/>')
            else:
                w, fs = L["w"], L["fs"]
                out.append(f'<rect x="{L["X"]-w/2:.2f}" y="{L["Y"]+0.09*fs:.2f}" width="{w:.2f}" height="{0.06*fs:.2f}" fill="{L["color"]}"/>')
    out.append("</svg>")
    return "".join(out)

def write_html(meta):
    sec_of = lambda box: next(s for s in MAIN_SECTIONS if s[1] <= box[1] < s[2])
    parts = []
    for i, (sid, top, bottom) in enumerate(MAIN_SECTIONS):
        if sid == "ubicacion":
            parts.append(ubicacion_html(meta["_ubicacion"])); continue
        h = bottom - top
        lazy = "eager" if i < 2 else "lazy"
        items = []
        order = 0
        for name, m in meta.items():
            if name.startswith("_") or m["kind"] == "intro" or sec_of(m["box"])[0] != sid: continue
            box, kind = m["box"], m["kind"]
            alt = "" if kind == "form" and name != "rsvp_boton" else html.escape(m["alt"], quote=True)
            img = (f'<img src="assets/img/el_{name}.webp" alt="{alt}" loading="{lazy}" decoding="async">'
                   if m["image"] else "")
            inner = img + text_html(m)
            style = place(box, top, h)
            if kind == "button-map":
                items.append(f'<a class="el reveal hit" id="mapsLink" href="#" target="_blank" rel="noopener" style="{style};--d:{order % 4}">{inner}</a>')
            elif kind == "form":
                tag = "button" if name == "rsvp_boton" else "div"
                extra = ' type="submit" id="rsvpSubmit"' if tag == "button" else ""
                items.append(f'<{tag} class="el reveal f-{name}"{extra} style="{style};--d:{order % 4}">{inner}</{tag}>')
            elif kind == "plain":
                items.append(f'<div class="el" style="{style}">{inner}</div>')
            else:
                items.append(f'<div class="el {kind}" style="{style};--d:{order % 4}">{inner}</div>')
            order += 1
        items.extend(SPECIAL.get(sid, lambda t, hh: [])(top, h))
        body = "\n  ".join(items)
        if sid == "rsvp":
            body = f'<form id="rsvpForm" class="rsvp-form" novalidate>\n  {body}\n  </form>'
        parts.append(
            f'<section class="sec" id="{sid}" style="aspect-ratio:{WIDTH}/{h}">\n'
            f'  <img class="bg" src="assets/img/sec_{sid}.webp" alt="" width="{WIDTH}" height="{h}" loading="{lazy}" decoding="async">\n  '
            + body + "\n</section>")
    tpl = (ROOT / "tools" / "template.html").read_text()
    out = tpl.replace("<!--SECTIONS-->", "\n".join(parts))
    out = out.replace("<!--MODAL-->", modal_html(meta["_ubicacion"]))
    out = out.replace("{{SITE_URL}}", SITE_URL)
    m1, m2 = meta["env_text"]["box"], meta["partners_text"]["box"]
    out = out.replace("{{ENV_TEXT}}", text_html(meta["env_text"], "env-text",
                      place(m1, ENVELOPE[0], ENVELOPE[1]-ENVELOPE[0])))
    out = out.replace("{{PARTNERS_TEXT}}", text_html(meta["partners_text"], "partners-text",
                      f"top:{pct(m2[1]-PARTNERS[0], PARTNERS[1]-PARTNERS[0])};--w:{(m2[2]-m2[0])/WIDTH:.4f}"))
    s = SEAL; out = out.replace("{{SEAL_STYLE}}", area(s["cx"]-s["r"], s["cy"]-s["r"], s["cx"]+s["r"], s["cy"]+s["r"], 0, ENVELOPE[1]))
    (ROOT / "index.html").write_text(out)


def player_items(top, h):
    a = lambda *xy: area(*xy, top, h)
    D = DISC
    return [
        f'<img class="disc" id="disc" src="assets/img/disco.webp" alt="" style="{a(D["cx"]-D["r"], D["cy"]-D["r"], D["cx"]+D["r"], D["cy"]+D["r"])}">',
        f'<button class="pbtn" id="likeBtn" aria-label="Me gusta" aria-pressed="false" style="{a(455, 3708, 516, 3766)}"><svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.6-9.6-9.2C1 8.6 3 5 6.6 5c2.1 0 3.6 1.2 4.4 2.6h2C13.8 6.2 15.3 5 17.4 5 21 5 23 8.6 21.6 11.8 19.5 16.4 12 21 12 21z"/></svg></button>',
        f'<button class="pbtn" id="prevBtn" aria-label="Retroceder 10 segundos" style="{a(560, 3712, 608, 3764)}"></button>',
        f'<button class="play" id="playBtn" aria-label="Reproducir" style="{a(635, 3692, 725, 3782)}"><svg class="i-play" viewBox="0 0 24 24"><path d="M8 5.5v13l10.5-6.5z"/></svg><svg class="i-pause" viewBox="0 0 24 24"><path d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg></button>',
        f'<button class="pbtn" id="nextBtn" aria-label="Adelantar 10 segundos" style="{a(752, 3712, 800, 3764)}"></button>',
        f'<a class="pbtn" id="dlBtn" href="#" download aria-label="Descargar la canción" style="{a(852, 3711, 905, 3764)}"></a>',
        f'<div class="progress" style="{a(462, 3806, 900, 3842)}"><input type="range" id="seek" min="0" max="1000" value="0" step="1" aria-label="Posición de la canción"></div>',
    ]

def rsvp_items(top, h):
    a = lambda *xy: area(*xy, top, h)
    return [
        f'<input class="name" id="rsvpName" name="nombre" autocomplete="name" required aria-label="Tu nombre" style="{a(84, 12366, 1020, 12450)}">',
        f'<label class="opt" style="{a(84, 12594, 1000, 12646)}"><input type="radio" name="asistencia" value="si" required><span class="dot" style="left:{(124-84)/(1000-84)*100:.3f}%"></span><span class="sr">¡Acepto con mucho gusto!</span></label>',
        f'<label class="opt" style="{a(84, 12646, 1000, 12698)}"><input type="radio" name="asistencia" value="no"><span class="dot" style="left:{(124-84)/(1000-84)*100:.3f}%"></span><span class="sr">Lamentablemente, no podré asistir.</span></label>',
        f'<div class="rsvp-msg" id="rsvpMsg" role="status" aria-live="polite" style="{a(80, 12360, 1000, 12900)}"></div>',
    ]

def countdown_items(top, h):
    a = lambda *xy: area(*xy, top, h)
    cols = [(137, "d"), (388, "h"), (650, "m"), (929, "s")]
    out = [f'<div class="cd" style="{a(0, 13915, 1080, 14025)}" aria-live="off">']
    for cx, k in cols:
        out.append(f'<span class="num" id="cd-{k}" style="left:{cx/WIDTH*100:.3f}%">00</span>')
    for cx in (275, 503, 780):
        out.append(f'<span class="colon" style="left:{cx/WIDTH*100:.3f}%">:</span>')
    out.append('</div>')
    return ["".join(out)]

SPECIAL = {"player": player_items, "rsvp": rsvp_items, "cuenta": countdown_items}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else "invitacion_digital.pdf")
