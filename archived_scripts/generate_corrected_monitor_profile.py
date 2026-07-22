#!/usr/bin/env python3
"""generate_monitor_profile.py
Requires psychopy in the path (because it is calling psychopy's own calibration routines)
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
import os
import sys
sys.modules['psychopy.alerts'] = type(sys)('psychopy.alerts')
sys.modules['psychopy.alerts'].alert = lambda *args, **kwargs: print(f"Alert: {args[0]}")
sys.modules['psychopy.alerts'].catalog = {}
# Optionally prepend a local PsychoPy source checkout (set PSYCHOPY_SRC to its path).
_psychopy_src = os.environ.get('PSYCHOPY_SRC')
if _psychopy_src:
    sys.path.insert(0, _psychopy_src)
import argparse
import datetime as _dt
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
    ts = _dt.datetime.now().strftime("%Y%m%d")
    name = args.name or f"AutoMonitor_{ts}" # If you don't pass a name then it makes a default one. It will overwrite anything else you made that day! 
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
    if hasattr(args, 'notes') and args.notes:
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
    # Rescale each of the R, G, and B spectra separately by their own peak
    rgb_resampled /= np.max(rgb_resampled, axis=0)

    if hasattr(mon, "setSpectra"):
        mon.setSpectra(new_nm, rgb_resampled.T)
    else:
        mon.currentCalib.update(spectraNM=new_nm, spectraRGB=rgb_resampled.T)


    # Human spectral cone functions are in human_data/ss10q_1.csv
    # load them in and compute LMS2RGB to set this matrix directly
    cone_csv = Path(__file__).parent / "human_data" / "ss10q_1.csv"
    if cone_csv.exists():
        cone_df = pd.read_csv(cone_csv)
        # Check if the file has the expected columns
        if not {'wavelength', 'L', 'M', 'S'}.issubset(cone_df.columns):
            # Set the columns to the expected ones
            cone_df.columns = ['wavelength', 'L', 'M', 'S']
        # Expect columns: wavelength, L, M, S
        cone_nm = cone_df['wavelength'].values
        cone_lms = cone_df[['L', 'M', 'S']].values.T  # shape: (3, N)
        cone_lms = 10** cone_lms

        # Interpolate cone functions to match new_nm
        interp_cone = interp1d(cone_nm, cone_lms, kind='linear', axis=1, bounds_error=False, fill_value=0)
        # The original sensitivity functions in cone_lms are log10 scaled - make them linear after interpolation


        cone_lms_resampled = interp_cone(new_nm)  # shape: (3, len(new_nm))
        # Compute LMS2RGB matrix using least squares
        # Find matrix M such that cone_lms_resampled.T @ M ≈ rgb_resampled
        # So, M = np.linalg.lstsq(cone_lms_resampled.T, rgb_resampled, rcond=None)[0]
        # replace any NaN values in rgb_resampled with 0
        rgb_resampled = np.nan_to_num(rgb_resampled, nan=0.0)
        # replace any NaN values in cone_lms_resampled with 0
        cone_lms_resampled = np.nan_to_num(cone_lms_resampled, nan=0.0)
        # Plot the resampled cone functions and RGB SPDs on the same graph
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 6))
        plt.plot(new_nm, rgb_resampled[:, 0], label='R (resampled)', color='red')
        plt.plot(new_nm, rgb_resampled[:, 1], label='G (resampled)', color='green')
        plt.plot(new_nm, rgb_resampled[:, 2], label='B (resampled)', color='blue')
        plt.plot(new_nm, cone_lms_resampled[0], '--', label='L-cone (resampled)', color='orange')
        plt.plot(new_nm, cone_lms_resampled[1], '--', label='M-cone (resampled)', color='purple')
        plt.plot(new_nm, cone_lms_resampled[2], '--', label='S-cone (resampled)', color='cyan')
        plt.xlabel('Wavelength (nm)')
        plt.ylabel('Relative Power / Sensitivity')
        plt.title('Resampled RGB SPDs and Human Cone Functions')
        plt.legend()
        plt.grid(True)
        plt.tight_layout()  
        plt.show()
        # If rgb_resampled and cone_lms_resampled.T are both square (same number of wavelengths),
        # you can compute the matrix directly using np.linalg.inv:
        # Find matrix M such that cone_lms_resampled.T @ M = rgb_resampled
        # So, M = np.linalg.inv(cone_lms_resampled.T) @ rgb_resampled

        #Show the shape of the two arrays - they should be nWavelengths x 3
        print(f"Shape of cone_lms_resampled: {cone_lms_resampled.shape}")
        print(f"Shape of rgb_resampled: {rgb_resampled.shape}")  

   
        # Compute the LMS2RGB matrix (3x3) using least squares
        # Find matrix M such that cone_lms_resampled.T @ M ≈ rgb_resampled
        # So, M = np.linalg.lstsq(cone_lms_resampled.T, rgb_resampled, rcond=None)[0]
        RGB2LMS = rgb_resampled.T @ cone_lms_resampled.T
        print(f"RGB2LMS matrix shape: {RGB2LMS.shape}")  # Should be (3, 3)
        print(f'RGB2LMS matrix:\n{RGB2LMS}')
        M = np.linalg.pinv(RGB2LMS)  # shape: (3, 3)
        M=M*100  # Scale the matrix to make it more readable
        mon.setLMS_RGB(M.T)
        print(f'Matrix LMS2RGB set from human cone data:\n {M.T}')
        print("✔ LMS2RGB matrix set from human cone data.")
    else:
        print("⚠ human_data/ss10q_1.csv not found; using default LMS2RGB.")

    mon.setDKL_RGB(makeDKL2RGB(new_nm, rgb_resampled.T))
    mon.setGamma(np.asarray(gamma_vals, float))
    mon.setLineariseMethod(0)
    mon.setPsychopyVersion(_psy_version)
    mon.calibrationDate = _dt.datetime.now().timestamp()
    mon.currentCalib['calibrated'] = True
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
