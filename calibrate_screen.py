
"""
calibrate_screen.py
-------------------

Monitor / projector calibration script
======================================

Performs:
    • Gamma‑transfer measurement for R, G, B and combined guns (W)
    • Full spectral capture at each brightness level
    • Parameter extraction (γ, k, b) with bounded least‑squares
    • Data export to NPZ (binary) + human‑readable CSV
    • Publication-ready PNG plots of gamma curves and peak spectra

Usage
-----
Run from terminal:

    python calibrate_screen.py --levels 16 --int_us 100000

By default the PsychoPy window requests an identity gamma LUT (`gamma=1.0`)
while measuring, so the fitted gamma describes the uncorrected display path as
closely as the platform permits. Use `--native_gamma` to leave the OS/GPU gamma
table untouched.

Dependencies
------------
    • PsychoPy
    • Seabreeze (Ocean Optics spectrometers)
    • NumPy, SciPy, Matplotlib
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

import seabreeze

# Matplotlib in headless mode → PNGs, no GUI required
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GAMMA_ERROR_POLICY = "raise"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def generate_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def gamma_fn(x: np.ndarray, gamma: float, k: float, b: float) -> np.ndarray:
    """Parametric power‑law transfer: L = k·x^γ + b."""
    return k * np.power(x, gamma) + b


def fit_gamma(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Fit `gamma_fn` with constraints: γ ∈ [1, 4], k ≥ 0, b ≥ 0."""
    bounds = ([1.0, 0.0, 0.0], [4.0, np.inf, np.inf])
    popt, _ = curve_fit(gamma_fn, x, y, p0=[2.2, 1.0, 0.0], bounds=bounds)
    return tuple(popt)  # γ, k, b


def ensure_sorted(wls: np.ndarray, intens: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return arrays sorted by ascending wavelength."""
    order = np.argsort(wls)
    return wls[order], intens[order]


# ------------------------------------------------------------
# Acquisition
# ------------------------------------------------------------

def acquire_spectrum(spec, integration_us: int, retries: int = 3) -> tuple[np.ndarray, np.ndarray]:
    spec.integration_time_micros(integration_us)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            wls = spec.wavelengths()
            intens = spec.intensities()
            return ensure_sorted(wls, intens)
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            print(f"Spectrum read failed ({type(exc).__name__}: {exc}); retrying {attempt}/{retries - 1}")
            time.sleep(0.25)
    raise last_error

def save_final_spectra(outdir: Path, wls: np.ndarray, spectra: dict[str, list[np.ndarray]], timestamp: str) -> None:
    """Save final spectra for red, green, and blue channels to CSV."""
    filename = outdir / f"spectra_final_{timestamp}.csv"
    with open(filename, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["wavelength_nm", "R", "G", "B"])
        
        rs = spectra["R"][-1]  # Last measurement for 'R' at maximum drive level
        gs = spectra["G"][-1]  # Last measurement for 'G' at maximum drive level
        bs = spectra["B"][-1]  # Last measurement for 'B' at maximum drive level

        for wl, r, g, b in zip(wls, rs, gs, bs):
            writer.writerow([wl, r, g, b])

    print(f"Final spectra saved to {filename.resolve()}")


def save_run_summary(outdir: Path, timestamp: str, summary: dict[str, object]) -> None:
    """Save a small human-readable calibration run summary."""
    filename = outdir / f"run_summary_{timestamp}.txt"
    with open(filename, "w") as file:
        file.write("Screen calibration run summary\n")
        file.write("==============================\n\n")
        for key, value in summary.items():
            file.write(f"{key}: {value}\n")

    print(f"Run summary saved to {filename.resolve()}")



def main(
    levels: int,
    integration_us: int,
    outdir: str | Path,
    identity_gamma: bool = True,
    acquisition_retries: int = 3,
    backend: str = "pyseabreeze",
    screen: int = 0,
    fullscr: bool = False,
    settle_frames: int = 1,
):
    from psychopy import core, event, visual
    from psychopy import __version__ as psychopy_version

    if settle_frames < 0:
        raise ValueError("settle_frames must be 0 or greater.")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Instrument initialisation
    # -----------------------------------------------------------------
    if backend == "auto":
        last_err = None
        for candidate in ("pyseabreeze", "cseabreeze"):
            try:
                seabreeze.use(candidate)
                break
            except Exception as exc:
                last_err = exc
        else:
            raise RuntimeError(f"Could not initialize any seabreeze backend: {last_err}")
    else:
        seabreeze.use(backend)

    import seabreeze.spectrometers as sb

    devices = sb.list_devices()
    if not devices:
        raise RuntimeError("No Ocean Optics spectrometer detected.")
    spec = sb.Spectrometer(devices[0])
    print(f"Using spectrometer: {spec}")

    win_gamma = 1.0 if identity_gamma else None
    requested_window_size = (1000, 800)
    win = visual.Window(
        size=requested_window_size,
        color=(-1, -1, -1),
        units="pix",
        fullscr=fullscr,
        allowGUI=True,
        gamma=win_gamma,
        gammaErrorPolicy=GAMMA_ERROR_POLICY,
        screen=screen,
    )
    print(
        "Calibration window gamma:",
        "identity LUT requested (gamma=1.0)" if identity_gamma else "native OS/GPU LUT",
    )
    print("Calibration window mode:", "fullscreen" if fullscr else "windowed")
    print("Calibration target screen index:", screen)
    core.wait(0.5)
    actual_window_size = tuple(int(value) for value in win.size)
    try:
        actual_frame_rate = win.getActualFrameRate()
    except Exception as exc:
        print(f"Could not measure display refresh rate: {type(exc).__name__}: {exc}")
        actual_frame_rate = None

    prompt = visual.TextStim(
        win,
        text="Press any key to start calibration",
        color=(1, 1, 1),
        height=40,
    )
    prompt.draw()
    win.flip()
    event.clearEvents(eventType="keyboard")
    print("Calibration ready; press any key in the PsychoPy window to begin.")
    event.waitKeys()

    # -----------------------------------------------------------------
    # Experimental design
    # -----------------------------------------------------------------
    drive_levels = np.linspace(0.0, 1.0, levels)  # 0…1
    colours = ["R", "G", "B", "W"]          # measurement order

    gamma_curve: dict[str, list[float]] = {c: [] for c in colours}
    spectra: dict[str, list[np.ndarray]] = {c: [] for c in colours}

    # -----------------------------------------------------------------
    # Measurement loop
    # -----------------------------------------------------------------
    for lvl in drive_levels:
        for c in colours:
            if c == "R":
                rgb = (2 * lvl - 1, -1, -1)
            elif c == "G":
                rgb = (-1, 2 * lvl - 1, -1)
            elif c == "B":
                rgb = (-1, -1, 2 * lvl - 1)
            else:  # "W"
                rgb = (2 * lvl - 1,) * 3

            win.color = rgb
            win.flip()
            for _ in range(settle_frames):
                win.flip()

            wls, intens = acquire_spectrum(spec, integration_us, retries=acquisition_retries)
            gamma_curve[c].append(float(np.mean(intens)))
            spectra[c].append(intens)

    # Neutral background spectrum (level 0)
    dark = np.mean([spectra[c][0] for c in ["R", "G", "B"]], axis=0)

    # -----------------------------------------------------------------
    # Fit gamma parameters
    # -----------------------------------------------------------------
    params = {c: fit_gamma(drive_levels, gamma_curve[c]) for c in colours}

    # -----------------------------------------------------------------
    # Save data tables
    # -----------------------------------------------------------------
    ts = generate_timestamp()

    # 1 Binary NPZ
    np.savez(
        outdir / f"calibration_{ts}.npz",
        wavelengths=wls,
        drive_levels=drive_levels,
        gamma_curve=gamma_curve,
        spectra=spectra,
        dark=dark,
        params=params,
        meta=dict(timestamp=ts,
                  integration_us=integration_us,
                  levels=levels,
                  identity_gamma=identity_gamma,
                  window_gamma=win_gamma,
                  gamma_error_policy=GAMMA_ERROR_POLICY,
                  settle_frames=settle_frames,
                  acquisition_retries=acquisition_retries)
    )

    # 2 CSV exports
    with open(outdir / f"gamma_curve_{ts}.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["drive"] + colours)
        for i, lvl in enumerate(drive_levels):
            writer.writerow([lvl] + [gamma_curve[c][i] for c in colours])

    with open(outdir / f"spectra_{ts}.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wavelength_nm", "drive", "colour", "intensity"])
        for c in colours:
            for li, lvl in enumerate(drive_levels):
                for wl, val in zip(wls, spectra[c][li]):
                    writer.writerow([wl, lvl, c, val])

    with open(outdir / f"gamma_params_{ts}.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["colour", "gamma", "k", "b"])
        for c, (g, k, b) in params.items():
            writer.writerow([c, g, k, b])
    
    
    save_final_spectra(outdir, wls, spectra, ts)
    save_run_summary(
        outdir,
        ts,
        {
            "timestamp": ts,
            "screen_index": screen,
            "window_mode": "fullscreen" if fullscr else "windowed",
            "screen_size_pix": f"{actual_window_size[0]} x {actual_window_size[1]}",
            "requested_window_size_pix": f"{requested_window_size[0]} x {requested_window_size[1]}",
            "refresh_rate_hz": "unknown" if actual_frame_rate is None else f"{actual_frame_rate:.3f}",
            "levels": levels,
            "drive_levels": ", ".join(f"{level:.6g}" for level in drive_levels),
            "integration_time_us": integration_us,
            "settle_frames": settle_frames,
            "spectrometer_backend": backend,
            "spectrometer": spec,
            "identity_gamma_requested": identity_gamma,
            "window_gamma": win_gamma,
            "gamma_error_policy": GAMMA_ERROR_POLICY,
            "acquisition_retries": acquisition_retries,
            "psychopy_version": psychopy_version,
        },
    )

    # -----------------------------------------------------------------
    # Publication‑quality plots
    # -----------------------------------------------------------------
    plt.style.use("dark_background")

    # Gamma curve figure
    plt.figure(figsize=(6, 4))
    for c in colours:
        plt.plot(drive_levels, gamma_curve[c],c.lower(), marker="o", label=c)
    plt.xlabel("Drive (0–1)")
    plt.ylabel("Mean intensity (a.u.)")
    plt.title("Gamma curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / f"gamma_curve_{ts}.png", dpi=150)
    plt.close()

    # Spectra at maximum drive
    plt.figure(figsize=(6, 4))
    max_idx = -1  # last level corresponds to max drive
    for c in colours:
        plt.plot(wls, spectra[c][max_idx] - dark,c.lower(),label=c )
    plt.xlabel("Wavelength (nm)")
    plt.ylabel("Intensity (a.u.)")
    plt.title("Spectra at maximum drive")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outdir / f"spectra_max_{ts}.png", dpi=150)
    plt.close()

    print("Saved data and plots to", outdir.resolve())

    win.close()
    core.quit()


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Display calibration utility.")
    parser.add_argument("--levels", type=int, default=16,
                        help="Number of drive levels (default: 16)")
    parser.add_argument("--int_us", type=int, default=100_000,
                        help="Spectrometer integration‑time in μs (default: 100000 → 0.1 s)")
    parser.add_argument("--out", type=str, default="calibration_data",
                        help="Output directory (default: ./calibration_data)")
    parser.add_argument("--native_gamma", action="store_true",
                        help="Leave the OS/GPU gamma table untouched instead of requesting identity gamma.")
    parser.add_argument("--acquisition_retries", type=int, default=3,
                        help="Number of attempts for each spectrometer read (default: 3).")
    parser.add_argument("--backend", choices=["pyseabreeze", "cseabreeze", "auto"], default="pyseabreeze",
                        help="Seabreeze backend to use (default: pyseabreeze).")
    parser.add_argument("--screen", type=int, default=0,
                        help="Display index for PsychoPy window (default: 0).")
    parser.add_argument("--settle_frames", type=int, default=1,
                        help="Number of additional screen refreshes to wait after setting each colour before measuring (default: 1).")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--fullscr", action="store_true",
                            help="Run the calibration window in fullscreen mode.")
    mode_group.add_argument("--windowed", action="store_true",
                            help="Run the calibration window in windowed mode (default).")
    args = parser.parse_args()

    main(
        levels=args.levels,
        integration_us=args.int_us,
        outdir=args.out,
        identity_gamma=not args.native_gamma,
        acquisition_retries=args.acquisition_retries,
        backend=args.backend,
        screen=args.screen,
        fullscr=args.fullscr,
        settle_frames=args.settle_frames,
    )
