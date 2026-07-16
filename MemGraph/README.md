# MemGraph — Windows Memory & Hardware Widget for Local LLMs

A lightweight, professional desktop widget that shows your system memory — and
CPU, GPU, NPU and temperatures — as a **live, hand-painted graph**, purpose-built
for keeping an eye on memory pressure while running local LLMs (Ollama,
llama.cpp, LM Studio, …).

![The widget](assets/screenshot-widget.png)

- 📈 **Custom-painted live graph** — smooth curve, gradient glow, no clutter
  (no chart library; drawn with QPainter)
- 🧠 **Built for local LLMs** — watch **RAM**, **GPU VRAM** and your **model
  process** (e.g. `ollama.exe`) in real time
- 🧩 **Fully customisable metrics** — mix and match **RAM, CPU, GPU, NPU,
  process memory** and **CPU / GPU / memory temperatures** (shown when sensors
  expose them)
- 🎨 Frameless, glassy, drop-shadowed panel with **3 themes** — drag it
  anywhere, snaps to edges, remembers its position
- 🟢🟡🔴 Colour thresholds (green → amber → red) for both usage and temperature
- 🔒 **Single instance** — launching again just surfaces the running widget
- 🚀 **Modern setup wizard**, **autostart at login**, and a **system-tray** icon
- 🪶 Tiny footprint — a memory monitor that doesn't hog memory

| Widget themes | Setup wizard |
|---|---|
| ![Graphite theme](assets/screenshot-graphite.png) | ![Setup](assets/screenshot-setup.png) |

---

## Install with pip (recommended — no Smart App Control issues)

Because the `.exe` is unsigned, **Windows Smart App Control** blocks it. Installing
via pip avoids that entirely: the app runs through Python's own trusted
`python.exe`, which SAC allows.

```bash
pip install memgraph-widget          # core (RAM/CPU/GPU + graph + llama)
pip install "memgraph-widget[temps]" # + in-process CPU/GPU temperatures
python -m memgraph                    # launch the widget
```

For a console-less launch on Windows (no terminal window): `pythonw -m memgraph`
(or run the installed `memgraph-widget` GUI script). To start it at login, add
that command to your Startup folder.

> Run it as **`python -m memgraph`** rather than the generated `memgraph.exe`
> shim — the `-m` form is guaranteed to run through the trusted interpreter.

## Install the packaged .exe

1. Download **`MemGraph-Setup.exe`** — the login-free direct link:
   **https://github.com/priyansh19/HelloWorld/releases/download/memgraph-latest/MemGraph-Setup.exe**
2. Run it. The **setup wizard** opens: pick a folder, choose autostart / desktop
   shortcut, and click **Install**. No admin rights.
3. The widget launches and lives in your system tray. Right-click it (or the
   tray icon) → **Settings…** to choose metrics and styling.

> Because the exe is unsigned, **SmartScreen** warns (click *More info → Run
> anyway*) and **Smart App Control**, if on, blocks it outright with no bypass —
> use the pip install above instead.

### Updating

To update, just download the latest `MemGraph-Setup.exe` and run it again. Setup
detects the existing install, shows **Update**, stops the running widget,
overwrites the files **in place** (same folder), and relaunches — no need to
uninstall or delete anything first. Your settings
(`%LOCALAPPDATA%\MemGraph\config.json`) are kept.

## Build it yourself (Windows)

```bat
git clone <this repo>
cd HelloWorld\MemGraph
build.bat
```

`build.bat` creates a virtualenv, installs deps, runs the tests, and produces
`dist\MemGraph-Setup.exe`. Manual equivalent:

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q
pyinstaller --noconfirm MemGraph.spec
```

## Run from source (any OS with a display)

```bash
pip install -r requirements.txt
python -m memgraph --widget      # the widget
python -m memgraph --setup       # the installer UI
```

> The GUI needs a desktop session. The core logic (metrics, config, history) is
> fully unit-tested and runs headless.

---

## Metrics

Enable any combination from **Settings → Metrics**. The first enabled metric is
the primary one drawn as the big graph.

| Metric | Source | Notes |
|---|---|---|
| RAM | psutil | Always available |
| CPU | psutil | Total utilisation |
| VRAM | NVML (`nvidia-ml-py`) | NVIDIA only; else `n/a` |
| GPU | NVML, else GPU-engine perf counter | Utilisation % |
| NPU | Windows PDH perf counter | Best-effort (Windows 11); else `n/a` |
| Process | psutil | Tracks e.g. `ollama.exe` (with/without `.exe`) |
| CPU / Mem / GPU Temp | psutil sensors / NVML | Shown only when a sensor reports it |

Anything a machine can't read shows a muted **`n/a`** row — nothing crashes.

### Temperatures on Windows

Windows has **no built-in temperature API** (`psutil` can't read temps there,
and even Task Manager doesn't show CPU temp). MemGraph reads them itself,
best-effort, in this order:

1. **Built-in reader** — `LibreHardwareMonitorLib` is bundled inside MemGraph and
   read in-process (nothing for you to install or run). This covers CPU, GPU and
   board/memory temps.
2. **LibreHardwareMonitor / OpenHardwareMonitor via WMI** — if you happen to run
   either app, it's auto-detected too.
3. **ACPI thermal zone** — a last-resort CPU/system temperature.

**Admin note:** GPU temperature usually reads without admin, but **CPU and
motherboard/memory temperatures require a kernel driver that only loads with
administrator rights**. Use the widget's ⋯ menu → **“Enable full temperatures
(admin)”** to relaunch elevated (one UAC prompt) and those temps light up.

**Memory temp:** many systems have **no memory-temperature sensor in hardware**
(common except on some DDR5/enthusiast kits), so `Mem Temp` may stay `n/a` even
when everything else works. For NVIDIA GPUs, GPU temperature also comes straight
from NVML.

## Display modes

Toggle from the widget's ⋯ menu, the llama's right-click menu, or Settings →
Behaviour:

- **Llama (default)** — a tiny pixel llama lives on your taskbar and *is* the
  monitor: its **stride speed = CPU** (stroll → walk → gallop), its
  **saddle-pack swells** past the amber RAM threshold, it puts **shades on**
  while your tracked LLM process (e.g. `ollama.exe`) is running, and past the
  red threshold it **panics** (red tint, sweat, `!!`). Hover for a quick
  readout, **click it to pop the full stat card**, drag it anywhere along the
  taskbar. It occasionally wanders a few pixels when relaxed (toggleable).
- **Pinned** — the compact card stays on screen (drag it anywhere) until you
  hide or quit it.
- **Peek** — the card hides at the right screen edge as a slim vertical
  **MEMGRAPH** tab. Click the tab and it slides out into the foreground, stays
  for the auto-hide duration (default 2 min, and while you hover it), then slides
  back in. The slide is a fast 150 ms animation.

## Settings

Stored at `%LOCALAPPDATA%\MemGraph\config.json`, edited from the in-app dialog:
metrics selection, tracked process, refresh interval, history window, theme,
sparkline on/off, opacity, usage & temperature colour thresholds, always-on-top,
edge-snap, autostart and start-hidden.

## How autostart & install work

- **Install** copies the exe to `%LOCALAPPDATA%\Programs\MemGraph`, drops a
  Start-menu (and optional desktop) shortcut, and writes an install marker.
- **Autostart** registers `MemGraph.exe --widget` under
  `HKCU\…\CurrentVersion\Run` — no admin rights, cleanly removed when disabled.
- **Single instance** is enforced with a `QSharedMemory` claim + a local socket;
  a second launch pings the first to surface itself, then exits.

---

## Architecture

```
MemGraph/
  memgraph/
    metrics.py          # Metric model + providers (psutil / NVML / PDH), pure logic
    _perf.py            # Windows PDH reader for NPU / GPU-engine utilisation
    history.py          # fixed-size ring buffer backing the graph
    config.py           # dataclass config, JSON load/save, validation, migration
    autostart.py        # Windows Run-key management (no-op elsewhere)
    sparkline.py        # hand-painted smooth graph (QPainter)
    widget.py           # glassy frameless panel: hero value, sparkline, metric bars
    settings_dialog.py  # tabbed settings UI
    installer.py        # modern setup window + install logic
    single_instance.py  # QSharedMemory + local-socket single-instance guard
    tray.py             # system-tray icon + menu
    app.py              # mode dispatch (--setup/--widget) + wiring
  tests/                # pytest for the non-GUI logic
  MemGraph.spec         # PyInstaller build (-> MemGraph-Setup.exe)
  build.bat             # one-command local build
```

The non-GUI modules have **no Qt dependency**, so they're unit-tested on any OS
and in CI. The GUI is a thin, tested layer over that core.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q
```

CI (`.github/workflows/build-memgraph.yml`) runs the tests, builds
`MemGraph-Setup.exe` on a Windows runner, and publishes it to the
`memgraph-latest` GitHub Release for every push touching `MemGraph/`.

## Publish to PyPI

The package publishes via **PyPI Trusted Publishing** (OIDC) — no API token to
store. One-time setup on PyPI (project owner):

1. Create a PyPI account at https://pypi.org.
2. Go to **Your account → Publishing → Add a pending publisher** and enter:
   - **PyPI project name:** `memgraph-widget`
   - **Owner:** `priyansh19`  ·  **Repository:** `HelloWorld`
   - **Workflow name:** `publish-pypi.yml`  ·  **Environment:** `pypi`
3. In the GitHub repo, create an **Environment** named `pypi`
   (Settings → Environments).

Then publish by tagging a release:

```bash
git tag v1.1.0 && git push origin v1.1.0     # triggers .github/workflows/publish-pypi.yml
```

or run the **Publish to PyPI** workflow manually from the Actions tab. Build
locally with `python -m build` (outputs `dist/`).
