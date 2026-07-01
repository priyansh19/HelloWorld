<h1 align="center">MemGraph</h1>

<p align="center">
  A lightweight, professional Windows desktop widget that shows your system
  memory — plus CPU, GPU, NPU and temperatures — as a live, hand-painted graph.
  Purpose-built for keeping an eye on memory pressure while running local LLMs.
</p>

<p align="center">
  <img src="MemGraph/assets/screenshot-widget.png" width="360" alt="MemGraph widget">
</p>

## ⬇️ Download

**[Download MemGraph-Setup.exe »](https://github.com/priyansh19/HelloWorld/releases/download/memgraph-latest/MemGraph-Setup.exe)**

Run it, follow the setup wizard, and the widget installs itself (no admin
rights). Windows SmartScreen may warn because the exe is unsigned — click
**More info → Run anyway**.

## Features

- 📈 **Custom-painted live graph** — smooth curve with a gradient glow, no clutter
- 🧠 **Built for local LLMs** — track RAM, GPU VRAM and your model process (Ollama, llama.cpp, LM Studio)
- 🧩 **Customisable metrics** — RAM, CPU, GPU, NPU, process memory and CPU/GPU/memory temperatures
- 🎨 Frameless, glassy, drop-shadowed panel with 3 themes — drag anywhere, snaps to edges
- 🔒 **Single instance**, 🚀 **modern setup wizard**, **autostart at login**, system-tray icon
- 🪶 Tiny footprint — a memory monitor that doesn't hog memory

| Themes | Setup wizard |
|---|---|
| <img src="MemGraph/assets/screenshot-graphite.png" width="320"> | <img src="MemGraph/assets/screenshot-setup.png" width="320"> |

## Documentation & source

The full application, build instructions and architecture live in
**[`MemGraph/`](MemGraph/)** — see [MemGraph/README.md](MemGraph/README.md).

Builds are produced automatically on a Windows CI runner and published to the
[`memgraph-latest`](https://github.com/priyansh19/HelloWorld/releases/tag/memgraph-latest)
release.

## License

[MIT](LICENSE)
