# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure numpy image processing used by the baker.

Conventions: images are ``(height, width, channels)`` float32 arrays with row 0
at the *bottom* (Blender's pixel order).  Coverage/weight masks are
``(height, width)`` float32 arrays in ``[0, 1]``.  Nothing here imports ``bpy``.
"""

import numpy as np

_EPS = 1e-8
_CHUNK_ROWS = 512


# ----------------------------------------------------------------------------
# Resampling


def downsample(img, weight, factor):
    """Coverage-weighted box filter.

    Returns ``(colour, weight)`` where colour is un-premultiplied (pixels with
    zero coverage are 0) and weight is the mean coverage of each block.
    """
    if factor == 1:
        return img.astype(np.float32, copy=False), weight.astype(np.float32, copy=False)
    h, w, c = img.shape
    h2, w2 = h // factor, w // factor
    img = img[: h2 * factor, : w2 * factor]
    weight = weight[: h2 * factor, : w2 * factor]
    wsum = weight.reshape(h2, factor, w2, factor).sum(axis=(1, 3), dtype=np.float32)
    csum = (img * weight[..., None]).reshape(h2, factor, w2, factor, c).sum(axis=(1, 3), dtype=np.float32)
    out = np.zeros_like(csum)
    np.divide(csum, wsum[..., None], out=out, where=wsum[..., None] > 0)
    return out, wsum / float(factor * factor)


def decode_normals(rgb):
    return rgb * 2.0 - 1.0


def encode_normals(vec):
    return vec * 0.5 + 0.5


def normalize_vectors(vec, fallback=(0.0, 0.0, 1.0)):
    length = np.sqrt(np.einsum("...i,...i->...", vec, vec))
    out = np.empty_like(vec)
    good = length > 1e-6
    out[good] = vec[good] / length[good][:, None]
    out[~good] = fallback
    return out


def downsample_normals(rgb, weight, factor):
    """Box filter for encoded normals: decode, average, re-normalise, encode."""
    if factor == 1:
        return rgb, weight
    vec, w = downsample(decode_normals(rgb), weight, factor)
    return encode_normals(normalize_vectors(vec)), w


# ----------------------------------------------------------------------------
# Hole filling (push-pull / infinite padding)


def _half(color, known):
    """2x reduction: average of known children, plus 'any child known' flag."""
    h, w = known.shape
    ph, pw = h % 2, w % 2
    csum = color * known[..., None]
    wsum = known.astype(np.float32)
    if ph or pw:
        csum = np.pad(csum, ((0, ph), (0, pw), (0, 0)))
        wsum = np.pad(wsum, ((0, ph), (0, pw)))
        h, w = h + ph, w + pw
    c = csum.shape[2]
    csum = csum.reshape(h // 2, 2, w // 2, 2, c).sum(axis=(1, 3))
    wsum = wsum.reshape(h // 2, 2, w // 2, 2).sum(axis=(1, 3))
    avg = np.zeros_like(csum)
    np.divide(csum, wsum[..., None], out=avg, where=wsum[..., None] > 0)
    return avg, wsum > 0


def _upsample_rows(a, out_h):
    """Linear 2x upsampling along axis 0 (edge clamped)."""
    p = np.concatenate([a[:1], a, a[-1:]], axis=0)
    even = 0.75 * p[1:-1] + 0.25 * p[:-2]
    odd = 0.75 * p[1:-1] + 0.25 * p[2:]
    out = np.empty((a.shape[0] * 2,) + a.shape[1:], dtype=a.dtype)
    out[0::2] = even
    out[1::2] = odd
    return out[:out_h]


def _upsample(a, shape):
    rows = _upsample_rows(a, shape[0])
    cols = _upsample_rows(np.swapaxes(rows, 0, 1), shape[1])
    return np.swapaxes(cols, 0, 1)


def fill_holes(img, valid, region=None):
    """Fill pixels where ``valid`` is False by pull-push interpolation.

    The array is modified **in place** and returned.  ``region`` limits which
    invalid pixels get replaced (default: all of them).  Valid pixels are never
    touched.  Works for any channel count and runs in O(n).
    """
    valid = valid.astype(bool, copy=False)
    if valid.all() or not valid.any():
        return img
    h, w, _ = img.shape
    levels = []
    color, known = _half(img, valid)
    while True:
        levels.append((color, known))
        if known.shape[0] == 1 and known.shape[1] == 1:
            break
        color, known = _half(color, known)
    coarse = levels[-1][0]
    for color, known in reversed(levels[:-1]):
        up = _upsample(coarse, known.shape)
        coarse = np.where(known[..., None], color, up)
    del levels
    # The finest level is assembled in row chunks to keep memory low at 8K+.
    target = ~valid if region is None else (~valid & region.astype(bool, copy=False))
    ch = coarse.shape[0]
    for y0 in range(0, h, _CHUNK_ROWS):
        y1 = min(h, y0 + _CHUNK_ROWS)
        rows_needed = target[y0:y1]
        if not rows_needed.any():
            continue
        cy0 = max(0, y0 // 2 - 1)
        cy1 = min(ch, (y1 + 1) // 2 + 1)
        up = _upsample(coarse[cy0:cy1], ((cy1 - cy0) * 2, w))
        off = y0 - cy0 * 2
        block = up[off : off + (y1 - y0)]
        img[y0:y1][rows_needed] = block[rows_needed]
    return img


def apply_background(img, valid, background):
    out = img.copy()
    out[~valid.astype(bool)] = np.asarray(background, np.float32)[: img.shape[2]]
    return out


# ----------------------------------------------------------------------------
# Derived maps


def _shift(a, dy, dx):
    """Shift a 2D array with edge clamping."""
    h, w = a.shape
    ys = np.clip(np.arange(h) - dy, 0, h - 1)
    xs = np.clip(np.arange(w) - dx, 0, w - 1)
    return a[ys][:, xs]


def _runs_forward(mask, limit):
    """For each pixel: how many consecutive True pixels follow it along axis 1 (capped)."""
    h, w = mask.shape
    xs = np.arange(w, dtype=np.int32)
    out = np.empty((h, w), np.uint8)
    for y0 in range(0, h, _CHUNK_ROWS):
        m = mask[y0:y0 + _CHUNK_ROWS]
        idx = np.where(m, np.int32(w), xs[None, :])
        nxt = np.minimum.accumulate(idx[:, ::-1], axis=1)[:, ::-1]
        out[y0:y0 + _CHUNK_ROWS] = np.clip(nxt - xs[None, :] - 1, 0, limit)
    return out


def _runs(mask, limit):
    """Run lengths inside ``mask`` towards +x, -x, +y and -y."""
    limit = min(int(limit), 255)
    right = _runs_forward(mask, limit)
    left = _runs_forward(mask[:, ::-1], limit)[:, ::-1]
    up = np.ascontiguousarray(_runs_forward(np.ascontiguousarray(mask.T), limit).T)
    down = np.ascontiguousarray(_runs_forward(np.ascontiguousarray(mask.T[:, ::-1]), limit)[:, ::-1].T)
    return right, left, up, down


def curvature_from_normal(normal_rgb, strength=1.0, radius=1.0, mask=None):
    """Edge curvature from an OpenGL tangent-space normal map.

    Convex edges become brighter than 0.5, concave ones darker.  ``radius`` is
    expressed in pixels at 1024px and scaled with resolution.  When ``mask``
    (UV island coverage) is given, a sample is only used if the straight path
    to it stays inside the island: tangent space is discontinuous across UV
    seams, so differences across a seam would show up as false lines.
    """
    h, w, _ = normal_rgb.shape
    nx = normal_rgb[..., 0] * 2.0 - 1.0
    ny = normal_rgb[..., 1] * 2.0 - 1.0
    res_scale = max(h, w) / 1024.0
    scale = max(1.0, res_scale) * max(radius, 0.1)
    # Slopes are per pixel; multiplying by a resolution-relative reference
    # width keeps the look identical at 1K, 2K, 4K...
    reference = 8.0 * res_scale
    radii = [max(1, int(round(mult * scale))) for mult in (1.0, 2.0, 4.0)]
    if mask is None:
        runs = None
    else:
        runs = _runs(mask.astype(bool, copy=False), max(radii))

    def sample(a, dy, dx, run):
        shifted = _shift(a, dy, dx)
        if runs is None:
            return shifted
        return np.where(run >= max(abs(dy), abs(dx)), shifted, a)

    curv = np.zeros((h, w), np.float32)
    for r, weight in zip(radii, (0.5, 0.3, 0.2)):
        if runs is None:
            right = left = up = down = None
        else:
            right, left, up, down = runs
        dnx = sample(nx, 0, -r, right) - sample(nx, 0, r, left)
        dny = sample(ny, -r, 0, up) - sample(ny, r, 0, down)
        curv += weight * (dnx + dny) / (2.0 * r)
    curv *= reference
    return np.clip(0.5 + 0.5 * strength * curv, 0.0, 1.0)[..., None].astype(np.float32)


def remap_pointiness(raw, strength=1.0):
    """Cycles pointiness is centred around 0.5 with a tiny range; expand it."""
    return np.clip(0.5 + (raw - 0.5) * 8.0 * strength, 0.0, 1.0).astype(np.float32)


def height_from_positions(p_high, p_low, n_low, valid, range_mode="AUTO", value_range=0.1):
    """Signed distance along the low-poly normal, normalised to [0, 1] (0.5 = surface)."""
    n = normalize_vectors(n_low.reshape(-1, 3)).reshape(n_low.shape)
    h = np.einsum("...i,...i->...", p_high - p_low, n).astype(np.float32)
    valid = valid.astype(bool)
    if range_mode == "AUTO":
        rng = float(np.abs(h[valid]).max()) if valid.any() else 0.0
        rng = rng if rng > 1e-9 else 1.0
    else:
        rng = max(float(value_range), 1e-9)
    out = np.clip(0.5 + 0.5 * h / rng, 0.0, 1.0)
    return out[..., None], rng


def normalize_positions(pos, lo, hi):
    lo = np.asarray(lo, np.float32)
    size = np.maximum(np.asarray(hi, np.float32) - lo, 1e-9)
    return np.clip((pos - lo) / size, 0.0, 1.0).astype(np.float32)


# ----------------------------------------------------------------------------
# Colour encoding


def linear_to_srgb(x):
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055).astype(np.float32)


def srgb_to_linear(x):
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4)).astype(np.float32)
