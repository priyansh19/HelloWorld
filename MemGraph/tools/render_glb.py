"""Bake a .glb car model into a transparent sprite atlas for the buddy widget.

Run this once on a development machine (not on the user's box) to turn a 3D model
into the PNG frames the widget draws. It renders the model from a ring of yaw
angles so the car can be shown driving left, driving right, and *rotating
through* the in-between angles when it drifts around at a screen edge.

    python tools/render_glb.py car.glb --out memgraph/assets/car --frames 24

Rendering runs in headless Chromium via three.js, screenshotting with a
transparent background, so no GPU, X server or modelling tool is needed. The
output is:

    <out>/car_00.png ... car_NN.png   one per yaw angle, background transparent
    <out>/atlas.json                  frame count + the exhaust anchor

The widget then picks the frame matching the car's heading; see
``memgraph/car_art.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:transparent;overflow:hidden}
canvas{display:block}
</style></head><body>
<script type="importmap">
{"imports": {"three": "./three.module.js", "three/addons/": "./jsm/"}}
</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const W = __W__, H = __H__;
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true,
                                          preserveDrawingBuffer:true});
renderer.setSize(W, H);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
// Neutral studio lighting: a key light high and to the left, a soft fill from
// the right, and hemisphere ambient so nothing goes pure black.
scene.add(new THREE.HemisphereLight(0xffffff, 0x404048, 1.05));
const key = new THREE.DirectionalLight(0xffffff, 2.1);
key.position.set(-3, 5, 3); scene.add(key);
const fill = new THREE.DirectionalLight(0xdfe6ff, 0.7);
fill.position.set(4, 2, -2); scene.add(fill);

const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 500);
const pivot = new THREE.Group();
scene.add(pivot);

window.__ready = false;
const WHEEL_RE = /wheel|tire|tyre|rim|rotor/i;
const NOT_WHEEL_RE = /calliper|caliper|arch|well|housing|guard/i;

new GLTFLoader().load('./model.glb', (gltf) => {
  const model = gltf.scene;
  model.updateMatrixWorld(true);

  // Orient so the car's longest horizontal axis runs along X (screen
  // horizontal). Models exported from FBX often arrive facing along Z.
  let box = new THREE.Box3().setFromObject(model);
  let size = box.getSize(new THREE.Vector3());
  if (size.z > size.x) {
    model.rotation.y = Math.PI / 2;
    model.updateMatrixWorld(true);
    box = new THREE.Box3().setFromObject(model);
    size = box.getSize(new THREE.Vector3());
  }

  // Centre on the bounding box so yaw spins about the car's own middle.
  const centre = box.getCenter(new THREE.Vector3());
  const holder = new THREE.Group();
  holder.add(model);
  model.position.sub(centre);
  pivot.add(holder);
  holder.updateMatrixWorld(true);

  // ---- wheels -------------------------------------------------------
  // Names in real models are unreliable (this one buries all four wheels
  // under a single "Combined" node), so pick wheel-ish meshes by name and
  // then cluster them into four quadrants by position. Each cluster gets a
  // pivot at its own hub centre, and rolls about the lateral axis (Z).
  const candidates = [];
  model.traverse((o) => {
    if (!o.isMesh) return;
    const n = (o.name || '') + '|' + ((o.parent && o.parent.name) || '');
    if (WHEEL_RE.test(n) && !NOT_WHEEL_RE.test(n)) candidates.push(o);
  });

  const wheelPivots = [];
  if (candidates.length) {
    const buckets = new Map();
    const tmp = new THREE.Box3();
    const c = new THREE.Vector3();
    for (const m of candidates) {
      tmp.setFromObject(m);
      if (tmp.isEmpty()) continue;
      tmp.getCenter(c);
      const key = (c.x >= 0 ? 'F' : 'R') + (c.z >= 0 ? 'L' : 'R');
      if (!buckets.has(key)) buckets.set(key, {meshes: [], sum: new THREE.Vector3(), n: 0});
      const b = buckets.get(key);
      b.meshes.push(m); b.sum.add(c); b.n++;
    }
    for (const b of buckets.values()) {
      const hub = b.sum.clone().divideScalar(Math.max(1, b.n));
      const wp = new THREE.Group();
      wp.position.copy(hub);
      holder.add(wp);
      wp.updateMatrixWorld(true);
      for (const m of b.meshes) wp.attach(m);   // preserves world transform
      wheelPivots.push(wp);
    }
  }
  window.__wheelCount = wheelPivots.length;

  // ---- camera -------------------------------------------------------
  // Frame for the worst case so the car never clips while rotating.
  const radius = Math.max(size.x, size.z) * 0.5;
  camera.left = -radius * 1.04; camera.right = radius * 1.04;
  camera.top = size.y * 0.62;   camera.bottom = -size.y * 0.62;
  camera.position.set(0, 0, radius * 6);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();

  window.__setPose = (yawDeg, spinDeg) => {
    pivot.rotation.y = yawDeg * Math.PI / 180;
    const s = spinDeg * Math.PI / 180;
    for (const wp of wheelPivots) wp.rotation.z = s;
    renderer.render(scene, camera);
  };
  window.__ready = true;
}, undefined, (e) => { window.__error = String(e); });
</script></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path, help="the .glb / .gltf file")
    ap.add_argument("--out", type=Path, required=True,
                    help="output directory for the frames")
    ap.add_argument("--frames", type=int, default=24,
                    help="yaw angles around the car (default 24)")
    ap.add_argument("--spins", type=int, default=6,
                    help="wheel-rotation phases, applied only at the driving "
                         "yaw angles (default 6)")
    ap.add_argument("--spin-yaws", default="all",
                    help="yaw angles (degrees) that get spin phases, or 'all' "
                         "(default) so the wheels turn at every heading")
    ap.add_argument("--format", default="webp", choices=("webp", "png"),
                    help="frame format; webp is ~4x smaller with alpha intact")
    ap.add_argument("--quality", type=int, default=92,
                    help="webp quality (default 92)")
    ap.add_argument("--spin-arc", type=float, default=72.0,
                    help="degrees the wheel sweeps across the spin phases; "
                         "one spoke pitch, so 72 for a 5-spoke rim")
    ap.add_argument("--width", type=int, default=640,
                    help="frame width in pixels (default 640)")
    ap.add_argument("--height", type=int, default=260)
    ap.add_argument("--exhaust", default="0.06,0.86",
                    help="exhaust anchor as x,y fractions of the frame")
    args = ap.parse_args()

    if not args.model.is_file():
        print(f"no such model: {args.model}", file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright first", file=sys.stderr)
        return 2

    three_dir = _find_three()
    if three_dir is None:
        print("three.js not found — run: npm i three", file=sys.stderr)
        return 2

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stage = out / ".stage"
    stage.mkdir(exist_ok=True)
    shutil.copy(three_dir / "build" / "three.module.js", stage / "three.module.js")
    # GLTFLoader pulls in sibling addon modules, so stage the whole jsm tree and
    # let an import map resolve both "three" and "three/addons/".
    jsm_dst = stage / "jsm"
    if not jsm_dst.is_dir():
        shutil.copytree(three_dir / "examples" / "jsm", jsm_dst)
    shutil.copy(args.model, stage / "model.glb")
    (stage / "index.html").write_text(
        _HTML.replace("__W__", str(args.width)).replace("__H__", str(args.height)),
        encoding="utf-8")

    frames = max(1, args.frames)
    spins = max(1, args.spins)
    spin_counts: dict[int, int] = {}
    # Screenshots always land as PNG; convert afterwards if webp was asked for.
    shot_dir = out if args.format == "png" else (out / ".png")
    shot_dir.mkdir(parents=True, exist_ok=True)
    # ES modules are blocked by CORS over file://, so serve the stage locally.
    server, port = _serve(stage)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=_chromium_path(),
                args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader",
                      "--disable-gpu-sandbox", "--no-sandbox"])
            page = browser.new_page(viewport={"width": args.width,
                                              "height": args.height})
            page.goto(f"http://127.0.0.1:{port}/index.html")
            page.wait_for_function("window.__ready === true || window.__error",
                                   timeout=60_000)
            err = page.evaluate("window.__error || null")
            if err:
                print(f"model failed to load: {err}", file=sys.stderr)
                browser.close()
                return 1
            wheels = page.evaluate("window.__wheelCount || 0")
            print(f"wheel groups found: {wheels}")
            # Yaw indices that get several wheel phases: the side-on headings.
            all_yaws = str(args.spin_yaws).strip().lower() == "all"
            spin_idx = set()
            if not all_yaws:
                for deg in str(args.spin_yaws).split(","):
                    deg = deg.strip()
                    if deg:
                        spin_idx.add(round(float(deg) / 360.0 * frames) % frames)
            for i in range(frames):
                yaw = 360.0 * i / frames
                n = spins if (all_yaws or i in spin_idx) else 1
                for j in range(n):
                    spin = args.spin_arc * j / n
                    page.evaluate(f"window.__setPose({yaw}, {spin})")
                    page.screenshot(path=str(shot_dir / f"car_{i:02d}_{j:02d}.png"),
                                    omit_background=True)
                spin_counts[i] = n
            browser.close()
    finally:
        server.shutdown()

    if args.format == "webp":
        _to_webp(shot_dir, out, args.quality)
        shutil.rmtree(shot_dir, ignore_errors=True)
    ext = args.format
    ex = _exhaust_anchor(out / f"car_00_00.{ext}", args.exhaust)
    (out / "atlas.json").write_text(json.dumps({
        "frames": frames,
        "spin_counts": {str(k): v for k, v in sorted(spin_counts.items())},
        "spin_arc": args.spin_arc,
        "width": args.width,
        "height": args.height,
        "exhaust": {"x": ex[0], "y": ex[1]},
        "pattern": "car_{yaw:02d}_{spin:02d}." + ext,
        "note": "yaw 0 faces +X (screen right); yaw increases counter-clockwise",
    }, indent=2), encoding="utf-8")
    shutil.rmtree(stage, ignore_errors=True)
    print(f"wrote {frames} frames to {out}")
    return 0


def _to_webp(src_dir: Path, dst_dir: Path, quality: int) -> None:
    """Re-encode the PNG screenshots as WebP — same alpha, about a quarter the
    size, which keeps the shipped atlas small."""
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    dst_dir.mkdir(parents=True, exist_ok=True)
    for png in sorted(src_dir.glob("car_*.png")):
        img = QtGui.QImage(str(png))
        if img.isNull():
            continue
        img.save(str(dst_dir / (png.stem + ".webp")), "WEBP", quality)


def _convert_to_webp(out: Path) -> None:
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtGui
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    for png in sorted(out.glob("car_*.png")):
        img = QtGui.QImage(str(png))
        if img.isNull():
            continue
        if img.save(str(png.with_suffix(".webp")), "WEBP", 90):
            png.unlink()


def _exhaust_anchor(side_frame: Path, fallback: str) -> tuple[float, float]:
    """Locate the exhaust as fractions of the frame.

    The side-on frame has the car's tail at screen left, so the tips sit just
    inside the opaque bounding box at the bottom-left. Measuring the box beats
    hardcoding, because the model's margin depends on its proportions.
    """
    try:
        import os as _os
        _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6 import QtGui
        app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
        img = QtGui.QImage(str(side_frame))
        if img.isNull():
            raise ValueError
        w, h = img.width(), img.height()
        x0, y1 = w, -1
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() > 16:
                    if x < x0:
                        x0 = x
                    if y > y1:
                        y1 = y
        if x0 >= w or y1 < 0:
            raise ValueError
        return ((x0 + 0.03 * w) / w, (y1 - 0.06 * h) / h)
    except Exception:
        vals = [float(v) for v in str(fallback).split(",")]
        return vals[0], vals[1]


def _serve(directory: Path):
    """Serve *directory* on a free localhost port in a daemon thread."""
    import functools
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler,
                                directory=str(directory))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _find_three() -> Path | None:
    here = Path(__file__).resolve()
    for base in [here.parent, here.parent.parent, Path.cwd()]:
        cand = base / "node_modules" / "three"
        if (cand / "build" / "three.module.js").is_file():
            return cand
    return None


def _chromium_path() -> str | None:
    root = Path("/opt/pw-browsers")
    if not root.is_dir():
        return None
    for pat in ("chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"):
        hits = sorted(root.glob(pat))
        if hits:
            return str(hits[-1])
    return None


if __name__ == "__main__":
    raise SystemExit(main())
