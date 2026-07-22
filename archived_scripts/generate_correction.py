#!/usr/bin/env python3
"""Generate spectrometer/light-pipe correction factors from a calibrated lamp."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_lamp_reference(path: Path) -> pd.DataFrame:
    """Load a two-column lamp reference file: wavelength and true intensity."""
    return pd.read_csv(path, sep=r"\s+", header=None, names=["wavelength", "true_intensity"])


def load_lamp_measurement(path: Path) -> pd.DataFrame:
    """Load repeated lamp measurements and average all intensity columns."""
    df = pd.read_csv(path)
    wavelength_col = "wavelength_nm" if "wavelength_nm" in df.columns else df.columns[0]
    intensity_cols = [col for col in df.columns if col != wavelength_col]
    if not intensity_cols:
        raise ValueError(f"No intensity columns found in {path}")

    out = pd.DataFrame({"wavelength": df[wavelength_col]})
    out["avg_measured"] = df[intensity_cols].mean(axis=1)
    return out


def normalize(values: pd.Series) -> pd.Series:
    values = values - values.min()
    max_value = values.max()
    if max_value == 0:
        raise ValueError("Cannot normalize a flat/zero spectrum.")
    return values / max_value


def generate_correction(
    lamp_file: Path,
    measurement_file: Path,
    output_file: Path,
    start_nm: float,
    stop_nm: float,
    step_nm: float,
    plot_file: Path | None,
) -> pd.DataFrame:
    lamp_df = load_lamp_reference(lamp_file)
    meas_df = load_lamp_measurement(measurement_file)

    lamp_df["true_norm"] = normalize(lamp_df["true_intensity"])
    meas_df["measured_norm"] = normalize(meas_df["avg_measured"])

    wavelengths = np.arange(start_nm, stop_nm + step_nm, step_nm)
    lamp_interp = np.interp(wavelengths, lamp_df["wavelength"], lamp_df["true_norm"])
    meas_interp = np.interp(wavelengths, meas_df["wavelength"], meas_df["measured_norm"])

    with np.errstate(divide="raise", invalid="raise"):
        correction_factor = lamp_interp / meas_interp

    out_df = pd.DataFrame(
        {
            "wavelength": wavelengths,
            "correction_factor": correction_factor,
        }
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_file, index=False)

    if plot_file:
        plot_file.parent.mkdir(parents=True, exist_ok=True)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        ax1.plot(lamp_df["wavelength"], lamp_df["true_norm"], label="True lamp", marker="o")
        ax1.plot(meas_df["wavelength"], meas_df["measured_norm"], label="Measured lamp", marker="x")
        ax1.plot(wavelengths, lamp_interp, label="Interpolated true", linestyle="--")
        ax1.plot(wavelengths, meas_interp, label="Interpolated measured", linestyle="--")
        ax1.set_ylabel("Normalized intensity")
        ax1.set_title("Lamp Reference vs Measurement")
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.plot(wavelengths, correction_factor, marker="s", color="tab:green")
        ax2.set_xlabel("Wavelength (nm)")
        ax2.set_ylabel("Correction factor")
        ax2.set_title("Spectral Correction Factor")
        ax2.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(plot_file, dpi=160)
        plt.close(fig)

    return out_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate wavelength correction factors from a lamp reference and measured lamp spectrum."
    )
    parser.add_argument("--lamp-file", type=Path, required=True, help="Two-column lamp reference file.")
    parser.add_argument("--measurement-file", type=Path, required=True, help="Measured lamp CSV.")
    parser.add_argument("--out", type=Path, required=True, help="Output correction_factors CSV.")
    parser.add_argument("--plot", type=Path, help="Optional diagnostic plot path.")
    parser.add_argument("--start-nm", type=float, default=380, help="First output wavelength.")
    parser.add_argument("--stop-nm", type=float, default=740, help="Last output wavelength.")
    parser.add_argument("--step-nm", type=float, default=5, help="Output wavelength step.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot = args.plot
    if plot is None:
        plot = args.out.with_suffix(".png")
    correction = generate_correction(
        lamp_file=args.lamp_file,
        measurement_file=args.measurement_file,
        output_file=args.out,
        start_nm=args.start_nm,
        stop_nm=args.stop_nm,
        step_nm=args.step_nm,
        plot_file=plot,
    )
    print(f"Saved {len(correction)} correction factors to {args.out}")
    print(f"Saved diagnostic plot to {plot}")
