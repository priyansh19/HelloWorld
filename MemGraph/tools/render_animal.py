"""Bake a rigged, animated .glb animal into a transparent walk/run sprite atlas.

Companion to ``render_glb.py`` (which bakes a car's yaw ring + wheel spin). An
animal doesn't turn in place or spin wheels — it plays a skeletal *walk cycle*
seen from the side, facing right, and the widget mirrors it to walk left. So
this tool samples each named animation clip (Walk, Run, …) across its duration
into transparent frames.

    python tools/render_animal.py Fox.glb --out memgraph/assets/fox \\
        --clips Walk,Run --frames 16

Runs in headless Chromium via three.js with an AnimationMixer, screenshotting
with a transparent background — no GPU, X server or 3D tool needed. Output:

    <out>/<clip>_00.webp ...      one per sampled frame, background transparent
    <out>/atlas.json              clip -> frame count, plus the aspect + feet

All frames of all clips are cropped to one shared bounding box, so the animal
never jitters vertically and switching Walk<->Run doesn't jump.
"""

from __future__ import annotations

import argparse
import functools
import json
import shutil
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
scene.add(new THREE.HemisphereLight(0xffffff, 0x45454c, 1.15));
const key = new THREE.DirectionalLight(0xffffff, 2.0);
key.position.set(-3, 5, 3); scene.add(key);
const fill = new THREE.DirectionalLight(0xdfe6ff, 0.65);
fill.position.set(4, 2, -2); scene.add(fill);

const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 5000);

window.__ready = false;
window.__clips = [];
new GLTFLoader().load('./model.glb', (gltf) => {
  const model = gltf.scene;
  model.updateMatrixWorld(true);

  // Orient so the animal's long axis runs along X (screen horizontal), facing
  // +X = screen-right. Rigged animals commonly face +Z on export.
  let box = new THREE.Box3().setFromObject(model);
  let size = box.getSize(new THREE.Vector3());
  if (size.z > size.x) {
    model.rotation.y = Math.PI / 2;
    model.updateMatrixWorld(true);
    box = new THREE.Box3().setFromObject(model);
    size = box.getSize(new THREE.Vector3());
  }
  const centre = box.getCenter(new THREE.Vector3());
  model.position.sub(centre);
  scene.add(model);
  model.updateMatrixWorld(true);

  // Frame the whole body with a little margin; the shared post-crop tightens it.
  const halfW = Math.max(size.x, size.z) * 0.56;
  camera.left = -halfW; camera.right = halfW;
  camera.top = size.y * 0.62; camera.bottom = -size.y * 0.62;
  camera.position.set(0, 0, Math.max(size.x, size.z) * 6);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();

  const mixer = new THREE.AnimationMixer(model);
  window.__clips = gltf.animations.map(a => ({name: a.name, dur: a.duration}));
  window.__play = (name, t) => {
    mixer.stopAllAction();
    const clip = THREE.AnimationClip.findByName(gltf.animations, name);
    if (!clip) { window.__error = 'no clip: ' + name; return; }
    mixer.clipAction(clip).play();
    mixer.setTime(0);
    mixer.update(t);           // advance to the sample time
    renderer.render(scene, camera);
  };
  window.__ready = true;
}, undefined, (e) => { window.__error = String(e); });
</script></body></html>
"""


def _serve(directory: Path):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
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


def _chromium() -> str | None:
    root = Path("/opt/pw-browsers")
    for pat in ("chromium-*/chrome-linux/chrome", "chromium/chrome-linux/chrome"):
        hits = sorted(root.glob(pat))
        if hits:
            return str(hits[-1])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--clips", default="Walk,Run",
                    help="comma-separated clip names, or 'all'")
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=320)
    ap.add_argument("--format", default="webp", choices=("webp", "png"))
    ap.add_argument("--quality", type=int, default=92)
    args = ap.parse_args()

    if not args.model.is_file():
        print(f"no such model: {args.model}", file=sys.stderr)
        return 2
    three = _find_three()
    if three is None:
        print("three.js not found — run: npm i three", file=sys.stderr)
        return 2
    from playwright.sync_api import sync_playwright

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    stage = out / ".stage"
    stage.mkdir(exist_ok=True)
    shutil.copy(three / "build" / "three.module.js", stage / "three.module.js")
    if not (stage / "jsm").is_dir():
        shutil.copytree(three / "examples" / "jsm", stage / "jsm")
    shutil.copy(args.model, stage / "model.glb")
    (stage / "index.html").write_text(
        _HTML.replace("__W__", str(args.width)).replace("__H__", str(args.height)),
        encoding="utf-8")

    frames = max(2, args.frames)
    raw: dict[tuple[str, int], str] = {}
    server, port = _serve(stage)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=_chromium(),
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
            available = {c["name"]: c["dur"]
                         for c in page.evaluate("window.__clips")}
            print(f"clips in model: {list(available)}")
            wanted = (list(available) if args.clips.strip().lower() == "all"
                      else [c.strip() for c in args.clips.split(",") if c.strip()])
            baked: dict[str, int] = {}
            for clip in wanted:
                dur = available.get(clip)
                if dur is None:
                    match = next((n for n in available
                                  if n.lower() == clip.lower()), None)
                    if match is None:
                        print(f"  ! clip {clip!r} not in model, skipping")
                        continue
                    clip, dur = match, available[match]
                for i in range(frames):
                    # sample [0, dur) — the last frame wraps to the first so the
                    # cycle loops seamlessly.
                    page.evaluate(f"window.__play({clip!r}, {dur * i / frames})")
                    p = str(out / f".raw_{clip}_{i:02d}.png")
                    page.screenshot(path=p, omit_background=True)
                    raw[(clip, i)] = p
                baked[clip] = frames
                print(f"  baked {clip}: {frames} frames (dur {dur:.3f}s)")
            browser.close()
    finally:
        server.shutdown()

    feet = _finish(out, raw, baked, args.format, args.quality)
    shutil.rmtree(stage, ignore_errors=True)
    (out / "atlas.json").write_text(json.dumps({
        "clips": baked,
        "pattern": "{clip}_{frame:02d}." + args.format,
        "feet_y": feet,     # ground line as a fraction of frame height
        "note": "frame faces screen-right; widget mirrors to walk left",
    }, indent=2), encoding="utf-8")
    print(f"wrote {sum(baked.values())} frames to {out}")
    return 0


def _finish(out: Path, raw: dict, baked: dict, fmt: str, quality: int) -> float:
    """Crop every frame to one shared bounding box, save as fmt, return the
    ground-line fraction (bottom of the shared box)."""
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])

    imgs = {k: QtGui.QImage(v) for k, v in raw.items()}
    x0 = y0 = 10**9
    x1 = y1 = -1
    for img in imgs.values():
        w, h = img.width(), img.height()
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() > 16:
                    x0 = min(x0, x); y0 = min(y0, y)
                    x1 = max(x1, x); y1 = max(y1, y)
    if x1 < x0:
        return 1.0
    rect = QtCore.QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    for (clip, i), img in imgs.items():
        crop = img.copy(rect)
        crop.save(str(out / f"{clip}_{i:02d}.{fmt}"), fmt.upper(), quality)
    for p in raw.values():
        try:
            Path(p).unlink()
        except OSError:
            pass
    return 1.0    # feet sit at the bottom of the shared crop


if __name__ == "__main__":
    raise SystemExit(main())
