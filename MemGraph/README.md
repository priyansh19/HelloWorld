# MemGraph — Windows Memory Widget for Local LLMs

A lightweight, always-on-top desktop widget that shows **live memory usage as a
rolling graph + percentage**, purpose-built to watch memory pressure while
running local LLMs (Ollama, llama.cpp, LM Studio, …).

- 📈 **Live graph** of the primary metric with a big % readout
- 🧠 Monitors **system RAM**, **NVIDIA GPU VRAM**, and a **chosen process**
  (e.g. `ollama.exe`) — VRAM is usually the real bottleneck for local models
- 🎨 Frameless, rounded, semi-transparent panel — **drag it anywhere**, snaps to
  screen edges, remembers its position
- 🟢🟡🔴 Colour thresholds (green → amber → red) as memory fills
- ⚙️ Full **settings** page (metrics, refresh rate, history length, opacity,
  theme, thresholds, autostart)
- 🚀 **Autostarts at login** (toggleable) and lives in the **system tray**
- 🪶 Tiny footprint (~40–60 MB) — a memory monitor that doesn't hog memory

---

## Quick start (pre-built .exe)

1. Grab `MemGraph.exe` from the **GitHub Actions** run for your branch:
   open the *Build MemGraph (Windows)* workflow → latest run → **Artifacts** →
   `MemGraph-windows`.
2. Unzip and double-click `MemGraph.exe`.
3. Right-click the widget (or the tray icon) → **Settings…** to configure.

No install, no admin rights. Autostart is enabled by default; turn it off in
Settings → *Behaviour*.

## Build it yourself (Windows)

```bat
git clone <this repo>
cd HelloWorld\MemGraph
build.bat
```

`build.bat` creates a virtualenv, installs deps, runs the tests, and produces
`dist\MemGraph.exe`.

Manual equivalent:

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
pyinstaller --noconfirm MemGraph.spec
```

## Run from source (any OS with a display)

```bash
pip install -r requirements.txt
python -m memgraph      # or: python run.py
```

> The GUI needs a desktop session. The core logic (sampling, config, history)
> is fully unit-tested and runs headless.

---

## Configuration

Settings are stored at `%LOCALAPPDATA%\MemGraph\config.json` and edited from the
in-app **Settings** dialog (right-click the widget → *Settings…*).

| Setting | What it does |
|---|---|
| Show RAM / VRAM / Process | Which metrics appear. Primary metric = first enabled |
| Process name | Process to track, e.g. `ollama.exe` (matches with/without `.exe`) |
| Refresh interval | Sampling period (250 ms – 10 s) |
| History length | Time window shown in the graph (30 s – 60 min) |
| Theme / Opacity | Dark or light; panel transparency |
| Amber / Red thresholds | Percentages at which the colour changes |
| Always on top / Snap to edges | Window behaviour |
| Start at login | Registers under `HKCU\…\Run` (no admin needed) |
| Start hidden | Launch to the tray only |

## How autostart works

MemGraph writes a `MemGraph` value under
`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run` pointing at the
running executable. Toggling *Start at login* in Settings adds/removes it. No
admin rights, nothing left behind if you disable it.

## GPU / VRAM notes

VRAM monitoring uses NVIDIA's NVML via `nvidia-ml-py`. On machines without an
NVIDIA GPU (or without the driver), the VRAM row shows **n/a** and everything
else keeps working. AMD/Intel VRAM is not yet supported.

---

## Architecture

```
MemGraph/
  memgraph/
    metrics.py         # sampling (psutil + pynvml) + pure interpretation logic
    history.py         # fixed-size ring buffer backing the graph
    config.py          # dataclass config, JSON load/save, validation
    autostart.py       # Windows Run-key management (no-op elsewhere)
    widget.py          # frameless draggable graph panel (Qt)
    settings_dialog.py # tabbed settings UI
    tray.py            # system-tray icon + menu
    app.py             # wiring + entrypoint
  tests/               # pytest for the non-GUI logic (43 tests)
  MemGraph.spec        # PyInstaller build definition
  build.bat            # one-command local build
```

The non-GUI modules have **no Qt dependency**, so they're unit-tested on any OS
and in CI. The GUI is a thin layer over that tested core.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI (`.github/workflows/build-memgraph.yml`) runs the tests and builds the `.exe`
on a Windows runner for every push touching `MemGraph/`.
