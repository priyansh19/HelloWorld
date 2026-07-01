"""PyInstaller / direct-run entry script.

Kept at the project root so ``pyinstaller run.py`` and ``python run.py`` both
work. The real logic lives in :mod:`memgraph.app`.
"""

from memgraph.app import main

if __name__ == "__main__":
    raise SystemExit(main())
