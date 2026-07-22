#!/usr/bin/env python3
"""generate_monitor_profile.py

Build a PsychoPy monitor profile (JSON) from spectral power distributions
and gamma‑transfer measurements.

**New behaviour**
-----------------
If *either* the spectra CSV or the gamma description is **omitted** on the
command line, the script will open a **GUI file‑picker** so that the user can
select the required file(s) interactively. *No* automatic guessing or fallback
files are used.

Typical usage
~~~~~~~~~~~~~
1. **Fully scripted** (no GUI):

   ```bash
   python generate_monitor_profile.py \
       --spectra_csv psycho_spectra_20250714_143522.csv \
       --gamma_grid gamma_grid_20250714_143522.csv \
       --name OLED_2025 --width_cm 59.7 --distance_cm 60 --size_pix 3840 2160
   ```

2. **Interactive** (let the picker ask for both files):

   ```bash
   python generate_monitor_profile.py --name QuickTest
   ```
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# GUI file picker (cross‑platform: Tk)
try:
    import tkinter as _tk
    from tkinter import filedialog as _fd
except ModuleNotFoundError:
    _tk = None  # headless fallback
    _fd = None

# PsychoPy imports ──────────────────────────────────────────────────────────
try:
    from psychopy import __version__ as _psy_version
    from psychopy.monitors import Monitor
    from psychopy.monitors.calibTools import makeDKL2RGB, makeLMS2RGB
except ModuleNotFoundError as err:
    sys.stderr.write("✖ PsychoPy is not installed. Run: pip install psychopy\n")
    raise err

# Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_WIDTH_CM = 50.0
_DEFAULT_DISTANCE_CM = 60.0
_DEFAULT_SIZE_PIX = (1920, 1080)
_DEFAULT_GAMMA = [2,2,2]
# CSV loaders ──────────────────────────────────────────────────────────────

def _detect_header(first_line: str) -> bool:
    """Return True if *first_line* contains any alphabetic character."""
    return any(ch.isalpha() for ch in first_line)


def _load_corrected_spectra(csv_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load wavelength and corrected RGB arrays from corrected spectra CSV."""
    df = pd.read_csv(csv_path)
    nm = df['wavelength'].values
    rgb = df[['R_corrected', 'G_corrected', 'B_corrected']].values
    return nm, rgb


def _load_gamma_grid(csv_path: Path) -> np.ndarray:
    """Load a 4×6 gamma grid, ignoring header if present."""
    with open(csv_path, "r", newline="") as f:
        first_line = f.readline()
    skip = 1 if _detect_header(first_line) else 0
    grid = np.genfromtxt(csv_path, delimiter=",", dtype=float, skip_header=skip)
    if grid.shape != (4, 6):
        raise ValueError("Gamma grid must be 4×6 numeric rows after header removal.")
    return grid


def _extract_gamma_from_params(csv_path: Path) -> List[float]:
    """Extract gamma values for R, G, B from gamma_params CSV."""
    df = pd.read_csv(csv_path)
    gamma_map = {row['colour'].strip().upper(): float(row['gamma']) for _, row in df.iterrows()}
    return [gamma_map[c] for c in ("R", "G", "B")]

# File‑picker helpers ───────────────────────────────────────────────────────

def _ask_open_csv(title: str) -> Optional[Path]:
    if _fd is None:
        return None  # headless environment; cannot prompt
    root = _tk.Tk()
    root.withdraw()
    path = _fd.askopenfilename(title=title, filetypes=[("CSV files", "*.csv")])
    root.destroy()
    return Path(path) if path else None

# Monitor builder ──────────────────────────────────────────────────────────

def _create_monitor(args: argparse.Namespace) -> None:
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = args.name or f"AutoMonitor_{ts}"
    width_cm = args.width_cm or _DEFAULT_WIDTH_CM
    distance_cm = args.distance_cm or _DEFAULT_DISTANCE_CM
    size_pix = tuple(args.size_pix) if args.size_pix else _DEFAULT_SIZE_PIX

    # ── spectra CSV ───────────────────────────────────────────────────────
    spectra_csv = Path(args.spectra_csv) if args.spectra_csv else None
    if spectra_csv is None:
        spectra_csv = _ask_open_csv("Select corrected spectra CSV (wavelength,R_corrected,G_corrected,B_corrected)")
    if spectra_csv is None:
        sys.exit("No corrected spectra CSV provided ‑ exiting.")
    print(f"✔ Corrected spectra file → {spectra_csv}")

    # ── gamma params ─────────────────────────────────────────────────────
    gamma_params_csv = Path(args.gamma_params) if hasattr(args, 'gamma_params') and args.gamma_params else None
    if gamma_params_csv is None:
        gamma_params_csv = _ask_open_csv("Select gamma_params CSV (colour,gamma,...)")
    if gamma_params_csv is None:
        sys.exit("No gamma_params CSV provided ‑ exiting.")
    gamma_vals = _extract_gamma_from_params(gamma_params_csv)
    print(f"✔ Gamma params → {gamma_params_csv}")

    # ── Build PsychoPy Monitor ───────────────────────────────────────────
    mon = Monitor(name=name, width=width_cm, distance=distance_cm)
    mon.setSizePix(size_pix)
    mon.setCalibDate(_dt.datetime.now().timestamp())
    if args.notes:
        mon.setNotes(args.notes)

    # Load corrected spectra
    nm, rgb = _load_corrected_spectra(spectra_csv)
    # Restrict nm and rgb to 380–720nm
    valid_range = (nm >= 380) & (nm <= 720)
    nm = nm[valid_range]
    rgb = rgb[valid_range]
    # Resample to 1nm intervals
    from scipy.interpolate import interp1d
    new_nm = np.arange(380, 721, 1)
    interp_func = interp1d(nm, rgb, axis=0, kind='linear', fill_value="extrapolate")
    rgb_resampled = interp_func(new_nm)
    rgb_resampled /= np.max(rgb_resampled)

    if hasattr(mon, "setSpectra"):
        mon.setSpectra(new_nm, rgb_resampled)
    else:
        mon.currentCalib.update(spectraNM=new_nm, spectraRGB=rgb_resampled)

    mon.setLMS_RGB(makeLMS2RGB(new_nm, rgb_resampled.T))
    mon.setDKL_RGB(makeDKL2RGB(new_nm, rgb_resampled.T))
    mon.setGamma(np.asarray(gamma_vals, float))
    mon.setLineariseMethod(0)
    mon.setPsychopyVersion(_psy_version)
    mon.save()

    profile_path = Path.home() / ".psychopy3" / "monitors" / f"{name}.json"
    print(f"✅ Monitor profile saved → {profile_path}")

    # Make plots of the monitor spectra....



# CLI parser ───────────────────────────────────────────────────────────────

def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a PsychoPy monitor profile from corrected SPD & gamma_params files.")
    p.add_argument("--name", help="Monitor name (<name>.json)")
    p.add_argument("--width_cm", type=float, help="Screen width in cm")
    p.add_argument("--distance_cm", type=float, help="Viewing distance in cm")
    p.add_argument("--size_pix", type=int, nargs=2, metavar=("W", "H"), help="Resolution in pixels")

    p.add_argument("--spectra_csv", type=Path, help="Spectra CSV (opens picker if omitted)")
    p.add_argument("--gamma_params", type=Path, help="gamma_params CSV (colour,gamma,...)")
    return p.parse_args()

# Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _create_monitor(_parse_cli())
