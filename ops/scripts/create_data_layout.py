#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import config as ctx


def create_data_layout() -> tuple[Path, ...]:
    created_dirs: list[Path] = []
    for directory in ctx.get_data_layout_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        created_dirs.append(directory)
    return tuple(created_dirs)


def main() -> int:
    created_dirs = create_data_layout()

    print("Data layout ensured")
    for directory in created_dirs:
        print(f"- {ctx.display_path(directory)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
