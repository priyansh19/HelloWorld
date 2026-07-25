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
new GLTFLoader().load('./model.glb', (gltf) => {
  const model = gltf.scene;

  // Centre the model on its own bounding box, then scale so its longest
  // horizontal axis fits the frame with a small margin.
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const centre = box.getCenter(new THREE.Vector3());
  model.position.sub(centre);
  pivot.add(model);

  const radius = Math.max(size.x, size.z) * 0.5;   // worst case when rotated
  const halfW = radius * 1.04;
  const halfH = (size.y * 0.5) * 1.10;
  camera.left = -halfW; camera.right = halfW;
  camera.top = halfH;   camera.bottom = -halfH;
  camera.position.set(0, 0, radius * 4 + size.z);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();

  window.__setYaw = (deg) => {
    pivot.rotation.y = deg * Math.PI / 180;
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
            for i in range(frames):
                yaw = 360.0 * i / frames
                page.evaluate(f"window.__setYaw({yaw})")
                page.screenshot(path=str(out / f"car_{i:02d}.png"),
                                omit_background=True)
            browser.close()
    finally:
        server.shutdown()

    ex = [float(v) for v in args.exhaust.split(",")]
    (out / "atlas.json").write_text(json.dumps({
        "frames": frames,
        "width": args.width,
        "height": args.height,
        "exhaust": {"x": ex[0], "y": ex[1]},
        "note": "frame 0 faces +X; yaw increases counter-clockwise",
    }, indent=2), encoding="utf-8")
    shutil.rmtree(stage, ignore_errors=True)
    print(f"wrote {frames} frames to {out}")
    return 0


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
