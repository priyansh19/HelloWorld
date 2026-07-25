"""Load a user-supplied car photo and turn it into a usable sprite.

The point is that you can hand this module a *screenshot* — a side-on photo of a
car on a plain backdrop, straight off a configurator page — and get back a clean
transparent sprite. No image editor needed.

Pipeline:

1. **Key the backdrop.** Flood-fill inward from the border, clearing every pixel
   that is within tolerance of the border colour. Because it only removes pixels
   *connected to the edge*, dark paint, tyres and window glass survive even when
   they are as dark as the backdrop.
2. **Keep the largest blob.** Configurator screenshots come with carousel arrows,
   watermarks and drop shadows floating in the backdrop. Only the biggest
   connected region of surviving pixels is kept, which is the car.
3. **Trim.** Crop to what is left so the sprite has no dead margin.
4. **Cache.** The keyed result is written next to the source as
   ``<name>.keyed.png`` and reused while the source is unchanged, so the flood
   fill runs once rather than on every launch.

If the source already has real transparency, keying is skipped and it is only
trimmed.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6 import QtCore, QtGui

# Bounds on the adaptive backdrop tolerance, per channel. The floor keeps a
# perfectly flat backdrop from leaving speckle; the ceiling stops a noisy one
# from swallowing dark bodywork and tyres.
_MIN_TOLERANCE = 14
_MAX_TOLERANCE = 60

# Cap the working width before the pure-Python flood fill (see prepare()).
_MAX_WORK_W = 800


def _looks_transparent(img: QtGui.QImage) -> bool:
    """True if the image already carries meaningful alpha."""
    if not img.hasAlphaChannel():
        return False
    w, h = img.width(), img.height()
    for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if img.pixelColor(x, y).alpha() < 8:
            return True
    return False


def _border_reference(img: QtGui.QImage) -> tuple[int, int, int, int]:
    """Backdrop colour plus an adaptive tolerance.

    Returns ``(r, g, b, tol_sq)``. The tolerance is derived from how much the
    border actually varies: a clean studio backdrop is near-uniform, so the
    tolerance stays tight. That matters because black tyres sit only ~15 levels
    off a near-black backdrop — a generous tolerance eats them.
    """
    w, h = img.width(), img.height()
    samples = []
    step = max(1, min(w, h) // 64)
    for x in range(0, w, step):
        for y in (0, h - 1):
            samples.append(img.pixelColor(x, y))
    for y in range(0, h, step):
        for x in (0, w - 1):
            samples.append(img.pixelColor(x, y))
    n = max(1, len(samples))
    r = sum(c.red() for c in samples) // n
    g = sum(c.green() for c in samples) // n
    b = sum(c.blue() for c in samples) // n
    spread = max(
        (abs(c.red() - r) + abs(c.green() - g) + abs(c.blue() - b)) / 3.0
        for c in samples) if samples else 0.0
    tol = max(_MIN_TOLERANCE, min(_MAX_TOLERANCE, 2.5 * spread + 6.0))
    return r, g, b, int(tol * tol * 3)


def _key_backdrop(img: QtGui.QImage) -> QtGui.QImage:
    """Clear backdrop-coloured pixels reachable from the border."""
    img = img.convertToFormat(QtGui.QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    br, bg, bb, tol_sq = _border_reference(img)

    ptr = img.bits()
    buf = memoryview(ptr).cast("B")
    stride = img.bytesPerLine()

    def is_backdrop(x: int, y: int) -> bool:
        o = y * stride + x * 4          # BGRA byte order
        db = buf[o] - bb
        dg = buf[o + 1] - bg
        dr = buf[o + 2] - br
        return dr * dr + dg * dg + db * db <= tol_sq

    seen = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def push(x: int, y: int) -> None:
        i = y * w + x
        if not seen[i] and is_backdrop(x, y):
            seen[i] = 1
            q.append((x, y))

    for x in range(w):
        push(x, 0); push(x, h - 1)
    for y in range(h):
        push(0, y); push(w - 1, y)

    while q:
        x, y = q.popleft()
        buf[y * stride + x * 4 + 3] = 0          # clear alpha
        if x > 0:
            push(x - 1, y)
        if x + 1 < w:
            push(x + 1, y)
        if y > 0:
            push(x, y - 1)
        if y + 1 < h:
            push(x, y + 1)
    return img


def _fill_interior_holes(img: QtGui.QImage) -> QtGui.QImage:
    """Re-opaque any cleared region that does not reach the image border.

    The flood fill can leak through a thin dark gap into an enclosed area — a
    wheel well, a window, a shadow under the sill. Anything cleared but walled
    in by the car is not backdrop, so put it back.
    """
    w, h = img.width(), img.height()
    buf = memoryview(img.bits()).cast("B")
    stride = img.bytesPerLine()

    def clear(x: int, y: int) -> bool:
        return buf[y * stride + x * 4 + 3] <= 8

    outside = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def push(x: int, y: int) -> None:
        i = y * w + x
        if not outside[i] and clear(x, y):
            outside[i] = 1
            q.append((x, y))

    for x in range(w):
        push(x, 0); push(x, h - 1)
    for y in range(h):
        push(0, y); push(w - 1, y)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                push(nx, ny)

    for y in range(h):
        row = y * stride
        for x in range(w):
            if clear(x, y) and not outside[y * w + x]:
                buf[row + x * 4 + 3] = 255
    return img


def _keep_largest_blob(img: QtGui.QImage) -> QtGui.QImage:
    """Drop everything but the biggest opaque region (kills stray UI bits)."""
    w, h = img.width(), img.height()
    buf = memoryview(img.bits()).cast("B")
    stride = img.bytesPerLine()

    def opaque(x: int, y: int) -> bool:
        return buf[y * stride + x * 4 + 3] > 8

    label = bytearray(w * h)
    best: list[tuple[int, int]] = []
    best_size = 0
    for sy in range(h):
        for sx in range(w):
            if label[sy * w + sx] or not opaque(sx, sy):
                continue
            comp: list[tuple[int, int]] = []
            q = deque([(sx, sy)])
            label[sy * w + sx] = 1
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        i = ny * w + nx
                        if not label[i] and opaque(nx, ny):
                            label[i] = 1
                            q.append((nx, ny))
            if len(comp) > best_size:
                best_size, best = len(comp), comp

    if not best:
        return img
    keep = bytearray(w * h)
    for x, y in best:
        keep[y * w + x] = 1
    for y in range(h):
        row = y * stride
        for x in range(w):
            if not keep[y * w + x]:
                buf[row + x * 4 + 3] = 0
    return img


def _trim(img: QtGui.QImage) -> QtGui.QImage:
    """Crop to the opaque bounding box."""
    w, h = img.width(), img.height()
    buf = memoryview(img.bits()).cast("B")
    stride = img.bytesPerLine()
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = y * stride
        for x in range(w):
            if buf[row + x * 4 + 3] > 8:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    if x1 < x0 or y1 < y0:
        return img
    return img.copy(QtCore.QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1))


def prepare(source: Path) -> QtGui.QImage | None:
    """Return a transparent, trimmed sprite for ``source`` (cached on disk)."""
    source = Path(source)
    if not source.is_file():
        return None
    cache = source.with_suffix(".keyed.png")
    try:
        if cache.is_file() and cache.stat().st_mtime >= source.stat().st_mtime:
            cached = QtGui.QImage(str(cache))
            if not cached.isNull():
                return cached
    except OSError:
        pass

    img = QtGui.QImage(str(source))
    if img.isNull():
        return None
    # The sprite is only ever a few hundred pixels wide, and the flood fill is
    # pure Python, so shrink oversized sources first. Keeps first-run keying to
    # about a second; the result is cached to disk anyway.
    if img.width() > _MAX_WORK_W:
        img = img.scaledToWidth(_MAX_WORK_W, QtCore.Qt.SmoothTransformation)

    if _looks_transparent(img):
        out = _trim(img.convertToFormat(QtGui.QImage.Format_ARGB32))
    else:
        out = _trim(_keep_largest_blob(
            _fill_interior_holes(_key_backdrop(img))))

    try:
        out.save(str(cache), "PNG")
    except OSError:
        pass
    return out
