#!/usr/bin/env python3
"""Measure the fibre/light-pipe path and optionally build correction factors."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seabreeze


def acquire_spectra(
    n_spectra: int,
    integration_us: int,
    delay_s: float,
    backend: str,
) -> tuple[np.ndarray, np.ndarray]:
    seabreeze.use(backend)
    from seabreeze.spectrometers import Spectrometer

    spec = Spectrometer.from_first_available()
    try:
        spec.integration_time_micros(integration_us)
        wavelengths = spec.wavelengths()
        intensities = np.empty((n_spectra, wavelengths.size))

        # One warm-up read helps older USB devices settle.
        spec.intensities(correct_dark_counts=False)
        for i in range(n_spectra):
            intensities[i] = spec.intensities(correct_dark_counts=False)
            time.sleep(delay_s)
    finally:
        spec.close()

    return wavelengths, intensities


def save_spectra(
    wavelengths: np.ndarray,
    intensities: np.ndarray,
    outdir: Path,
    prefix: str,
    plot: bool,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"{prefix}_{timestamp}.csv"

    df = pd.DataFrame({"wavelength_nm": wavelengths})
    for i in range(intensities.shape[0]):
        df[f"intensity_{i + 1}"] = intensities[i]
    df.to_csv(outfile, index=False)

    if plot:
        plotfile = outfile.with_suffix(".png")
        fig, ax = plt.subplots(figsize=(10, 6))
        for i in range(intensities.shape[0]):
            ax.plot(wavelengths, intensities[i], label=f"Spectrum {i + 1}")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity")
        ax.set_title("Repeated Spectrometer Measurements")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(plotfile, dpi=160)
        plt.close(fig)
        print(f"Saved plot to {plotfile}")

    return outfile


def _normalize(values: pd.Series) -> pd.Series:
    values = values - values.min()
    max_value = values.max()
    if max_value == 0:
        raise ValueError("Cannot normalize a flat/zero spectrum.")
    return values / max_value


def generate_correction_factors(
    lamp_file: Path,
    measurement_file: Path,
    output_file: Path,
    start_nm: float,
    stop_nm: float,
    step_nm: float,
    plot: bool,
) -> Path:
    lamp_df = pd.read_csv(lamp_file, sep=r"\s+", header=None, names=["wavelength", "true_intensity"])
    meas_df = pd.read_csv(measurement_file)

    wavelength_col = "wavelength_nm" if "wavelength_nm" in meas_df.columns else meas_df.columns[0]
    intensity_cols = [col for col in meas_df.columns if col != wavelength_col]
    if not intensity_cols:
        raise ValueError(f"No intensity columns found in {measurement_file}")

    meas_avg = pd.DataFrame({"wavelength": meas_df[wavelength_col]})
    meas_avg["avg_measured"] = meas_df[intensity_cols].mean(axis=1)

    lamp_norm = _normalize(lamp_df["true_intensity"])
    meas_norm = _normalize(meas_avg["avg_measured"])
    wavelengths = np.arange(start_nm, stop_nm + step_nm, step_nm)
    lamp_interp = np.interp(wavelengths, lamp_df["wavelength"], lamp_norm)
    meas_interp = np.interp(wavelengths, meas_avg["wavelength"], meas_norm)

    with np.errstate(divide="raise", invalid="raise"):
        correction_factor = lamp_interp / meas_interp

    output_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "wavelength": wavelengths,
            "correction_factor": correction_factor,
        }
    ).to_csv(output_file, index=False)

    if plot:
        plotfile = output_file.with_suffix(".png")
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        ax1.plot(lamp_df["wavelength"], lamp_norm, label="Lamp reference")
        ax1.plot(meas_avg["wavelength"], meas_norm, label="Measured through fibre")
        ax1.set_ylabel("Normalized intensity")
        ax1.set_title("Lamp Reference vs Fibre Measurement")
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        ax2.plot(wavelengths, correction_factor, color="tab:green")
        ax2.set_xlabel("Wavelength (nm)")
        ax2.set_ylabel("Correction factor")
        ax2.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(plotfile, dpi=160)
        plt.close(fig)
        print(f"Saved correction plot to {plotfile}")

    return output_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure repeated fibre/lamp spectra and optionally generate correction factors."
    )
    parser.add_argument("--n-spectra", type=int, default=10, help="Number of sequential spectra.")
    parser.add_argument("--integration-us", type=int, default=10_000, help="Integration time in microseconds.")
    parser.add_argument("--delay-s", type=float, default=0.01, help="Delay between spectra in seconds.")
    parser.add_argument("--outdir", type=Path, default=Path("calibration_data"), help="Output directory.")
    parser.add_argument("--prefix", default="oceanoptics_run", help="Output filename prefix.")
    parser.add_argument("--backend", default="pyseabreeze", choices=["pyseabreeze", "cseabreeze"], help="Seabreeze backend.")
    parser.add_argument("--no-plot", action="store_true", help="Do not save a PNG plot.")
    parser.add_argument("--lamp-file", type=Path, help="Optional two-column lamp reference file.")
    parser.add_argument("--correction-out", type=Path, help="Optional output correction_factors.csv path.")
    parser.add_argument("--start-nm", type=float, default=380, help="First correction wavelength.")
    parser.add_argument("--stop-nm", type=float, default=740, help="Last correction wavelength.")
    parser.add_argument("--step-nm", type=float, default=5, help="Correction wavelength step.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    wls, intens = acquire_spectra(
        n_spectra=args.n_spectra,
        integration_us=args.integration_us,
        delay_s=args.delay_s,
        backend=args.backend,
    )
    outfile = save_spectra(
        wavelengths=wls,
        intensities=intens,
        outdir=args.outdir,
        prefix=args.prefix,
        plot=not args.no_plot,
    )
    print(f"Saved {args.n_spectra} spectra to {outfile}")
    if args.lamp_file:
        correction_out = args.correction_out or outfile.with_name("correction_factors.csv")
        correction_file = generate_correction_factors(
            lamp_file=args.lamp_file,
            measurement_file=outfile,
            output_file=correction_out,
            start_nm=args.start_nm,
            stop_nm=args.stop_nm,
            step_nm=args.step_nm,
            plot=not args.no_plot,
        )
        print(f"Saved correction factors to {correction_file}")
