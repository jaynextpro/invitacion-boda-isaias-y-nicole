"""
Photo replacement helpers used by build_assets.py.

hd_swap     – the new file is a sharper copy of a photo already in the design.
              It's aligned to the design by feature matching (SIFT + RANSAC),
              then the design's colour grading / gradients are transferred onto
              it (low-frequency difference), and anything drawn over the photo
              in the design (flowers, frames…) is kept as-is.
window_fill – a different photo goes into a frame: it's cover-fitted, rotated to
              the window's angle and placed only where the old photo was visible.
"""
import cv2
import numpy as np


def _align(new_bgr, target_bgr):
    """Affine (scale+rotation+translation) mapping new -> target pixel coords."""
    k = min(1.0, 1.6 * max(target_bgr.shape[:2]) / max(new_bgr.shape[:2]))
    small = cv2.resize(new_bgr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    sift = cv2.SIFT_create(5000)
    g1 = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY); g2 = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)
    k1, d1 = sift.detectAndCompute(g1, None); k2, d2 = sift.detectAndCompute(g2, None)
    pairs = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    good = [a for a, b in pairs if a.distance < 0.75 * b.distance]
    if len(good) < 12:
        raise RuntimeError(f"photo does not match the design ({len(good)} matches)")
    src = np.float32([k1[a.queryIdx].pt for a in good]); dst = np.float32([k2[a.trainIdx].pt for a in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.5)
    if M is None or inl.sum() < 10:
        raise RuntimeError("could not align photo")
    M = M.copy(); M[:, :2] *= k            # express in original new-photo pixels
    return M, int(inl.sum())


def _warp(new_bgr, M, size):
    """Warp with a pre-resize so big downscales stay sharp and alias-free."""
    s = np.sqrt(abs(np.linalg.det(M[:, :2])))
    if s < 1:
        pre = cv2.resize(new_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        M = M.copy(); M[:, :2] /= s
        new_bgr = pre
    w, h = size
    img = cv2.warpAffine(new_bgr, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    cov = cv2.warpAffine(np.full(new_bgr.shape[:2], 255, np.uint8), M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    return img, cov.astype(np.float32) / 255


def _masked_blur(x, w, sigma):
    num = cv2.GaussianBlur(x * w[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(w, (0, 0), sigma)[..., None]
    return num / np.maximum(den, 1e-4)


def _features(rgb, xs, ys):
    """Colour polynomial (deg 2) + spatial terms (for gradients / vignettes)."""
    r, g, b = (rgb[:, i] / 255.0 for i in range(3))
    return np.stack([np.ones_like(r), r, g, b, r*r, g*g, b*b, r*g, r*b, g*b,
                     xs, ys, xs*xs, ys*ys, xs*ys, r*xs, r*ys, g*xs, g*ys, b*xs, b*ys], axis=1)


def hd_swap(target_rgb, new_rgb, region_mask=None, overlay_thresh=38):
    """target_rgb: HxWx3 uint8 crop of the design; new_rgb: the HD photo (RGB).
    region_mask: HxW float 0..1 where the photo may be replaced (default: all).

    1) align the HD photo to the design (feature matching)
    2) learn the design's colour grading as a colour mapping (+ smooth position
       terms), fitted only where the design really shows the photo. Being a
       function of colour, not of neighbours, it can't create halos at edges.
    3) whatever the mapping can't explain (flowers, frames drawn over the photo)
       is kept from the design."""
    tgt = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2BGR)
    new = cv2.cvtColor(new_rgb, cv2.COLOR_RGB2BGR)
    M, inliers = _align(new, tgt)
    h, w = tgt.shape[:2]
    warped, cov = _warp(new, M, (w, h))
    warped = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
    region = np.ones((h, w), np.float32) if region_mask is None else region_mask.astype(np.float32)
    valid = cv2.erode((cov > 0.99).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & (region > 0.5)

    T = target_rgb.astype(np.float32); W = warped.astype(np.float32)
    # compare at the design's (softer) detail level so sharper HD edges don't count as mismatch
    Tb = cv2.GaussianBlur(T, (0, 0), 2.5); Wb = cv2.GaussianBlur(W, (0, 0), 2.5)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xs_all = (xx / w - 0.5).ravel(); ys_all = (yy / h - 0.5).ravel()
    rng = np.random.default_rng(0)
    use = valid.copy()
    for _ in range(5):
        idx = np.flatnonzero(use.ravel())
        idx = rng.choice(idx, size=min(len(idx), 60000), replace=False)
        F = _features(Wb.reshape(-1, 3)[idx], xs_all[idx], ys_all[idx])
        coef, *_ = np.linalg.lstsq(F, Tb.reshape(-1, 3)[idx], rcond=None)
        mapped_b = (_features(Wb.reshape(-1, 3), xs_all, ys_all) @ coef).reshape(h, w, 3)
        resid = np.abs(Tb - mapped_b).max(axis=2)
        over = resid > overlay_thresh
        use = valid & ~cv2.dilate(over.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    # apply the mapping to the sharp HD pixels
    corrected = np.clip((_features(W.reshape(-1, 3), xs_all, ys_all) @ coef).reshape(h, w, 3), 0, 255)

    # overlay mask: confident seeds, grown into their soft (antialiased) edges
    seeds = (resid > overlay_thresh).astype(np.uint8)
    soft = (resid > overlay_thresh * 0.4).astype(np.uint8)
    n, lab = cv2.connectedComponents(cv2.dilate(soft, np.ones((3, 3), np.uint8)))
    grown = np.isin(lab, np.unique(lab[seeds > 0])) & (lab > 0)
    over = cv2.dilate(grown.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
    keep_design = cv2.GaussianBlur(over, (0, 0), 1.5)
    a = np.clip(cv2.GaussianBlur(valid.astype(np.float32), (0, 0), 1.5) * region * (1 - keep_design), 0, 1)[..., None]
    out = T * (1 - a) + corrected * a
    fit_err = float(np.median(resid[use]))
    stats = dict(inliers=inliers, scale=float(np.sqrt(abs(np.linalg.det(M[:, :2])))),
                 replaced=float(a.mean()), kept_overlay=float(over[valid].mean()), colour_fit_median_err=round(fit_err, 2))
    return out.astype(np.uint8), stats


def _photo_region(layer_rgba, bg_rgb):
    """Where the old photo is visible: the layer composited over the page
    background differs from the background alone. Frame ornaments and leaves are
    identical in both (they're drawn over the photo), so they fall outside.
    Returns (solid mask with holes filled, soft edge ramp)."""
    L = layer_rgba[..., :3].astype(np.float32); A = layer_rgba[..., 3:].astype(np.float32) / 255
    B = bg_rgb.astype(np.float32)
    diff = np.abs(L * A + B * (1 - A) - B).max(axis=2)
    m = cv2.morphologyEx((diff > 30).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    m = (lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    # fill holes (light parts of the old photo that happened to match the background)
    ff = m.copy(); h, w = m.shape
    cv2.floodFill(ff, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 1)
    solid = m | (1 - ff)
    ramp = np.clip((diff - 8) / 30, 0, 1)
    return solid.astype(bool), ramp


def _quad(mask):
    """Corners (tl, tr, br, bl) of a roughly rectangular mask: each side is a line
    fitted to its middle part (corners are notched by ornaments, leaves overlap
    the bottom-left), then neighbouring lines are intersected."""
    ys, xs = np.nonzero(mask); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    def fit(points):
        vx, vy, px, py = cv2.fitLine(np.float32(points), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        return np.array([px, py]), np.array([vx, vy])
    rows = [r for r in range(int(y0 + 0.25 * (y1 - y0)), int(y0 + 0.70 * (y1 - y0))) if mask[r].any()]
    cols = [c for c in range(int(x0 + 0.30 * (x1 - x0)), int(x0 + 0.70 * (x1 - x0))) if mask[:, c].any()]
    left = fit([(np.nonzero(mask[r])[0].min(), r) for r in rows])
    right = fit([(np.nonzero(mask[r])[0].max(), r) for r in rows])
    top = fit([(c, np.nonzero(mask[:, c])[0].min()) for c in cols])
    bottom = fit([(c, np.nonzero(mask[:, c])[0].max()) for c in cols])
    def meet(l1, l2):
        (p1, d1), (p2, d2) = l1, l2
        t = np.linalg.solve(np.array([d1, -d2]).T, p2 - p1)
        return p1 + t[0] * d1
    return [meet(top, left), meet(top, right), meet(bottom, right), meet(bottom, left)]


def window_fill(layer_rgba, bg_rgb, new_rgb, focus=(0.5, 0.45), bleed=1.01):
    """layer_rgba: the frame layer rendered alone (it holds the finished look of
    frame + old photo); bg_rgb: the page background under it (same crop).
    Returns a new RGBA layer where the new photo shows exactly where the old one
    did, in the same perspective; ornaments and leaves stay on top."""
    solid, ramp = _photo_region(layer_rgba, bg_rgb)
    tl, tr, br, bl = _quad(solid)
    cen = (tl + tr + br + bl) / 4
    tl, tr, br, bl = (cen + (p - cen) * bleed for p in (tl, tr, br, bl))
    win_w = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    win_h = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    angle = float(np.degrees(np.arctan2(tr[1] - tl[1], tr[0] - tl[0])))
    ph, pw = new_rgb.shape[:2]
    aspect = win_w / win_h
    cw, ch = (pw, pw / aspect) if pw / ph < aspect else (ph * aspect, ph)
    fx, fy = focus
    x0 = min(max(pw * fx - cw / 2, 0), pw - cw); y0 = min(max(ph * fy - ch / 2, 0), ph - ch)
    k = min(1.0, 1.25 * win_w / cw)                     # pre-shrink so the warp doesn't alias
    src_img = cv2.resize(new_rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    src = np.float32([[x0, y0], [x0 + cw, y0], [x0 + cw, y0 + ch], [x0, y0 + ch]]) * k
    P = cv2.getPerspectiveTransform(src, np.float32([tl, tr, br, bl]))
    h, w = bg_rgb.shape[:2]
    warped = cv2.warpPerspective(src_img, P, (w, h), flags=cv2.INTER_LANCZOS4,
                                 borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    # solid inside; at the rim follow how much the old photo showed (antialiased lip)
    inner = cv2.erode(solid.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
    a = np.maximum(inner, ramp * solid)
    a = cv2.GaussianBlur(a, (0, 0), 0.7)[..., None]
    L = layer_rgba[..., :3].astype(np.float32); A = layer_rgba[..., 3:].astype(np.float32) / 255
    out_rgb = L * (1 - a) + warped * a
    out_a = np.maximum(A, a)
    return (np.dstack([out_rgb, out_a[..., 0] * 255]).clip(0, 255).astype(np.uint8),
            dict(angle=round(angle, 2), window=(round(win_w), round(win_h))))
