from __future__ import annotations

import argparse
import json
from pathlib import Path

from psychopy import monitors


def inspect_monitor(monitor_name: str) -> int:
    mon = monitors.Monitor(monitor_name)

    monitor_dir = Path(monitors.calibTools.monitorFolder)
    monitor_file = monitor_dir / f"{monitor_name}.json"
    print("Monitor folder:", monitor_dir)
    print("Monitor file:", monitor_file, "| exists:", monitor_file.exists())

    if monitor_file.exists():
        with monitor_file.open("r") as f:
            raw = json.load(f)
        print("\nCalibrations stored in file:")
        for calib in raw.get("calibs", []):
            print("  name =", calib.get("name", "<none>"), "keys =", list(calib.keys()))

    print("\nmon.calibNames:", mon.calibNames)
    print("mon.currentCalibName:", mon.currentCalibName)
    print("keys in currentCalib:", list(mon.currentCalib.keys()))
    print("mon.getLMS_RGB():", mon.getLMS_RGB())
    print("mon.getDKL_RGB():", mon.getDKL_RGB())

    return 0 if monitor_file.exists() else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a PsychoPy monitor JSON/profile.")
    parser.add_argument("monitor_name", help="Monitor name as stored in PsychoPy.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(inspect_monitor(parse_args().monitor_name))
