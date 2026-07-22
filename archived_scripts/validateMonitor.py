from __future__ import annotations

import argparse

import numpy as np
from psychopy.monitors import Monitor


def validate_monitor(monitor_name: str) -> int:
    mon = Monitor(monitor_name)

    print("Monitor:", mon.name)
    print("Available calibration keys:", list(mon.currentCalib.keys()))

    missing = []
    for key in ["lms_rgb", "gamma", "calibrated"]:
        if key not in mon.currentCalib:
            missing.append(key)
            print(f"Missing required key: {key}")

    mat = mon.getLMS_RGB()
    print("LMS->RGB matrix:", mat)

    if mat is None:
        print("getLMS_RGB() returned None; spectra may be missing or invalid.")
        return 1

    rgb = np.eye(3) @ mat.T
    print("RGB from unit LMS:", rgb)
    print("In gamut for unit LMS inputs?", bool(np.all((rgb >= 0) & (rgb <= 1))))

    return 1 if missing else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a PsychoPy monitor profile.")
    parser.add_argument("monitor_name", help="Monitor name as stored in PsychoPy.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(validate_monitor(parse_args().monitor_name))
