#!/usr/bin/env python3
"""Create diagnostic plots from a display calibration output directory."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COLOURS = {
    "R": "red",
    "G": "green",
    "B": "blue",
    "W": "white",
}


def _latest(path: Path, pattern: str) -> Path:
    matches = sorted(path.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No {pattern} file found in {path}")
    return matches[-1]


def gamma_fn(x: np.ndarray, gamma: float, k: float, b: float) -> np.ndarray:
    return k * np.power(x, gamma) + b


def plot_gamma(outdir: Path, prefix: str) -> Path:
    gamma_curve = pd.read_csv(_latest(outdir, "gamma_curve_*.csv"))
    gamma_params = pd.read_csv(_latest(outdir, "gamma_params_*.csv"))

    dense_x = np.linspace(0, 1, 250)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_facecolor("#111111")
    fig.patch.set_facecolor("#111111")

    for colour, line_colour in COLOURS.items():
        if colour not in gamma_curve:
            continue
        row = gamma_params.loc[gamma_params["colour"] == colour]
        ax.plot(
            gamma_curve["drive"],
            gamma_curve[colour],
            "o",
            color=line_colour,
            label=f"{colour} measured",
            markersize=4,
        )
        if not row.empty:
            gamma, k, b = row[["gamma", "k", "b"]].iloc[0].astype(float)
            ax.plot(
                dense_x,
                gamma_fn(dense_x, gamma, k, b),
                "-",
                color=line_colour,
                alpha=0.8,
                label=f"{colour} fit gamma={gamma:.2f}",
            )

    ax.set_xlabel("Drive")
    ax.set_ylabel("Mean intensity (a.u.)")
    ax.set_title("Gamma Curves and Fits")
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    for item in [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels()]:
        item.set_color("white")
    legend = ax.get_legend()
    if legend:
        legend.get_frame().set_alpha(0.2)
        for text in legend.get_texts():
            text.set_color("white")
    fig.tight_layout()

    output = outdir / f"{prefix}_gamma_curves.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def plot_final_spectra(outdir: Path, prefix: str) -> Path:
    spectra = pd.read_csv(_latest(outdir, "spectra_final_*.csv"))

    fig, ax = plt.subplots(figsize=(9, 5))
    for colour, line_colour in [("R", "red"), ("G", "green"), ("B", "blue")]:
        ax.plot(spectra["wavelength_nm"], spectra[colour], color=line_colour, label=colour)

    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_title("Final RGB Spectra at Maximum Drive")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()

    output = outdir / f"{prefix}_final_spectra.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def plot_spectra_by_drive(outdir: Path, prefix: str) -> Path:
    matches = sorted(
        path for path in outdir.glob("spectra_*.csv") if not path.name.startswith("spectra_final_")
    )
    if not matches:
        raise FileNotFoundError(f"No spectra_*.csv file found in {outdir}")
    spectra = pd.read_csv(matches[-1])
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    for ax, colour, line_colour in zip(axes, ["R", "G", "B"], ["red", "green", "blue"]):
        subset = spectra[spectra["colour"] == colour]
        for drive, group in subset.groupby("drive"):
            ax.plot(
                group["wavelength_nm"],
                group["intensity"],
                color=line_colour,
                alpha=0.18 + 0.72 * float(drive),
                linewidth=0.8,
            )
        ax.set_ylabel(f"{colour} intensity")
        ax.grid(True, alpha=0.2)

    axes[-1].set_xlabel("Wavelength (nm)")
    fig.suptitle("RGB Spectra Across Drive Levels")
    fig.tight_layout()

    output = outdir / f"{prefix}_spectra_by_drive.png"
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output


def create_plots(outdir: Path, prefix: str) -> list[Path]:
    outdir = outdir.resolve()
    return [
        plot_gamma(outdir, prefix),
        plot_final_spectra(outdir, prefix),
        plot_spectra_by_drive(outdir, prefix),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot calibration diagnostics.")
    parser.add_argument("outdir", type=Path, help="Calibration output directory.")
    parser.add_argument("--prefix", default="diagnostic", help="Output filename prefix.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    for path in create_plots(args.outdir, args.prefix):
        print(path)
