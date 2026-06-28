#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
WORK = (ROOT / ".work").resolve()

if WORK.parent != ROOT.resolve() or WORK.name != ".work":
    raise SystemExit("refusing to clean an unexpected path")
if WORK.exists():
    shutil.rmtree(WORK)
    print(f"removed {WORK}")
else:
    print(f"clean-work: {WORK} does not exist")
