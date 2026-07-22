#!/usr/bin/env python3
"""Estimate luminance from Ocean Optics display calibration spectra.

This is a relative-to-absolute transfer:

1. Load a reference screen calibration measured through the same fibre and
   spectrometer geometry.
2. Compute a photopically weighted count index for its full-white spectrum.
3. Scale that index to a known photometer luminance.
4. Apply the same scale to other calibration files.

The estimate is intended for calibration runs made with the same optical path.
It normalizes by spectrometer integration time so runs with different exposure
times can be compared.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np


# CIE 1924 photopic luminous efficiency function, sampled every 5 nm.
# Values outside this table are treated as zero.
CIE_WAVELENGTHS_NM = np.arange(380.0, 781.0, 5.0)
CIE_PHOTOPIC_V_LAMBDA = np.array(
    [
        0.000039,
        0.000064,
        0.000120,
        0.000217,
        0.000396,
        0.000640,
        0.001210,
        0.002180,
        0.004000,
        0.007300,
        0.011600,
        0.016840,
        0.023000,
        0.029800,
        0.038000,
        0.048000,
        0.060000,
        0.073900,
        0.090980,
        0.112600,
        0.139020,
        0.169300,
        0.208020,
        0.258600,
        0.323000,
        0.407300,
        0.503000,
        0.608200,
        0.710000,
        0.793200,
        0.862000,
        0.914850,
        0.954000,
        0.980300,
        0.994950,
        1.000000,
        0.995000,
        0.978600,
        0.952000,
        0.915400,
        0.870000,
        0.816300,
        0.757000,
        0.694900,
        0.631000,
        0.566800,
        0.503000,
        0.441200,
        0.381000,
        0.321000,
        0.265000,
        0.217000,
        0.175000,
        0.138200,
        0.107000,
        0.081600,
        0.061000,
        0.044580,
        0.032000,
        0.023200,
        0.017000,
        0.011920,
        0.008210,
        0.005723,
        0.004102,
        0.002929,
        0.002091,
        0.001484,
        0.001047,
        0.000740,
        0.000520,
        0.000361,
        0.000249,
        0.000172,
        0.000120,
        0.000085,
        0.000060,
        0.000042,
        0.000030,
        0.000021,
        0.000015,
    ],
    dtype=float,
)


@dataclass(frozen=True)
class Calibration:
    path: Path
    wavelengths_nm: np.ndarray
    drive_levels: np.ndarray
    spectra: dict[str, list[np.ndarray]]
    dark: np.ndarray
    integration_us: float
    timestamp: str


@dataclass(frozen=True)
class SpectralCorrection:
    path: Path
    wavelengths_nm: np.ndarray
    factors: np.ndarray


def _npz_object(value: np.ndarray) -> object:
    return value.item() if value.shape == () else value


def load_calibration(path: Path) -> Calibration:
    data = np.load(path, allow_pickle=True)
    required = {"wavelengths", "drive_levels", "spectra", "dark", "meta"}
    missing = required.difference(data.files)
    if missing:
        raise ValueError(f"{path} is missing required NPZ entries: {sorted(missing)}")

    meta = _npz_object(data["meta"])
    if not isinstance(meta, dict):
        raise ValueError(f"{path} has an unsupported meta entry")

    integration_us = float(meta.get("integration_us", 0.0))
    if integration_us <= 0:
        raise ValueError(f"{path} does not record a positive integration_us value")

    spectra = _npz_object(data["spectra"])
    if not isinstance(spectra, dict):
        raise ValueError(f"{path} has an unsupported spectra entry")

    return Calibration(
        path=path,
        wavelengths_nm=np.asarray(data["wavelengths"], dtype=float),
        drive_levels=np.asarray(data["drive_levels"], dtype=float),
        spectra={str(key).upper(): value for key, value in spectra.items()},
        dark=np.asarray(data["dark"], dtype=float),
        integration_us=integration_us,
        timestamp=str(meta.get("timestamp", path.stem.removeprefix("calibration_"))),
    )


def load_spectral_correction(path: Path) -> SpectralCorrection:
    with open(path, newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"{path} is empty")
        fieldnames = {name.strip() for name in reader.fieldnames}
        required = {"wavelength", "correction_factor"}
        if not required.issubset(fieldnames):
            raise ValueError(f"{path} must contain wavelength and correction_factor columns")

        wavelengths: list[float] = []
        factors: list[float] = []
        for row in reader:
            wavelengths.append(float(row["wavelength"]))
            factors.append(float(row["correction_factor"]))

    if len(wavelengths) < 2:
        raise ValueError(f"{path} must contain at least two correction rows")

    order = np.argsort(wavelengths)
    return SpectralCorrection(
        path=path,
        wavelengths_nm=np.asarray(wavelengths, dtype=float)[order],
        factors=np.asarray(factors, dtype=float)[order],
    )


def photopic_weights(wavelengths_nm: np.ndarray, count_basis: str) -> np.ndarray:
    v_lambda = np.interp(
        wavelengths_nm,
        CIE_WAVELENGTHS_NM,
        CIE_PHOTOPIC_V_LAMBDA,
        left=0.0,
        right=0.0,
    )
    if count_basis == "energy":
        return v_lambda
    if count_basis == "photon":
        # Photon-count spectra need an energy-per-photon conversion. Constants
        # cancel during reference scaling, leaving the 1 / wavelength term.
        return np.divide(v_lambda, wavelengths_nm, out=np.zeros_like(v_lambda), where=wavelengths_nm > 0)
    raise ValueError(f"Unsupported count basis: {count_basis}")


def integrate_trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def spectrum_at_drive(
    calibration: Calibration,
    colour: str,
    requested_drive: float,
    subtract_dark: bool,
    clip_negative: bool,
) -> tuple[np.ndarray, float]:
    colour = colour.upper()
    if colour not in calibration.spectra:
        raise ValueError(f"{calibration.path} has no {colour!r} spectra")

    drive_index = int(np.argmin(np.abs(calibration.drive_levels - requested_drive)))
    actual_drive = float(calibration.drive_levels[drive_index])
    spectrum = np.asarray(calibration.spectra[colour][drive_index], dtype=float)
    if subtract_dark:
        spectrum = spectrum - calibration.dark
    if clip_negative:
        spectrum = np.maximum(spectrum, 0.0)
    return spectrum, actual_drive


def luminance_index(
    calibration: Calibration,
    colour: str,
    requested_drive: float,
    count_basis: str,
    subtract_dark: bool,
    clip_negative: bool,
    spectral_correction: SpectralCorrection | None,
) -> tuple[float, float]:
    spectrum, actual_drive = spectrum_at_drive(
        calibration=calibration,
        colour=colour,
        requested_drive=requested_drive,
        subtract_dark=subtract_dark,
        clip_negative=clip_negative,
    )
    signal_per_us = spectrum / calibration.integration_us
    correction_valid = np.ones_like(calibration.wavelengths_nm, dtype=bool)
    if spectral_correction is not None:
        correction_valid = (
            (calibration.wavelengths_nm >= spectral_correction.wavelengths_nm[0])
            & (calibration.wavelengths_nm <= spectral_correction.wavelengths_nm[-1])
        )
        correction_factor = np.interp(
            calibration.wavelengths_nm,
            spectral_correction.wavelengths_nm,
            spectral_correction.factors,
            left=np.nan,
            right=np.nan,
        )
        signal_per_us = signal_per_us * correction_factor

    weights = photopic_weights(calibration.wavelengths_nm, count_basis)
    valid = (
        (calibration.wavelengths_nm >= CIE_WAVELENGTHS_NM[0])
        & (calibration.wavelengths_nm <= CIE_WAVELENGTHS_NM[-1])
        & correction_valid
        & np.isfinite(signal_per_us)
        & np.isfinite(weights)
    )
    if int(valid.sum()) < 2:
        raise ValueError(f"{calibration.path} has fewer than two valid visible-wavelength samples")

    index = integrate_trapezoid(
        signal_per_us[valid] * weights[valid],
        calibration.wavelengths_nm[valid],
    )
    return index, actual_drive


def expand_targets(paths: Iterable[Path]) -> list[Path]:
    targets: list[Path] = []
    for path in paths:
        if path.is_dir():
            targets.extend(sorted(path.glob("calibration_*.npz")))
        else:
            targets.append(path)
    missing = [path for path in targets if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing target calibration file(s): {', '.join(str(path) for path in missing)}")
    if not targets:
        raise ValueError("No calibration files were provided")
    return targets


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_rows(rows: list[dict[str, object]]) -> None:
    print(f"{'estimated_cd_m2':>16}  {'colour':>6}  {'drive':>7}  target")
    for row in rows:
        print(
            f"{float(row['estimated_luminance_cd_m2']):16.3f}  "
            f"{str(row['colour']):>6}  "
            f"{float(row['actual_drive']):7.3f}  "
            f"{row['target_file']}"
        )


def parse_colours(value: str) -> list[str]:
    colours = [part.strip().upper() for part in value.split(",") if part.strip()]
    valid = {"R", "G", "B", "W"}
    invalid = [colour for colour in colours if colour not in valid]
    if invalid:
        raise argparse.ArgumentTypeError(f"Unsupported colour(s): {', '.join(invalid)}")
    if not colours:
        raise argparse.ArgumentTypeError("At least one colour must be provided")
    return colours


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate luminance from calibration NPZ spectra using a Minolta-anchored reference.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "targets",
        type=Path,
        nargs="+",
        help="Target calibration_*.npz file(s), or directories containing calibration_*.npz files.",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("calibration_data/viewpixx3dEEG60hz_300k/calibration_20260526_121957.npz"),
        help="Reference calibration NPZ measured with the same fibre/spectrometer path.",
    )
    parser.add_argument(
        "--reference-luminance-cd-m2",
        type=float,
        default=84.0,
        help="Known photometer luminance for the reference colour/drive.",
    )
    parser.add_argument(
        "--reference-colour",
        choices=["R", "G", "B", "W"],
        default="W",
        help="Reference spectrum colour to anchor to the photometer reading.",
    )
    parser.add_argument(
        "--colours",
        type=parse_colours,
        default=["W"],
        help="Comma-separated target spectra colours to estimate, e.g. R,G,B,W.",
    )
    parser.add_argument("--drive", type=float, default=1.0, help="Requested drive level.")
    parser.add_argument(
        "--count-basis",
        choices=["auto", "photon", "energy"],
        default="auto",
        help=(
            "Use photon-count weighting V(lambda)/lambda, energy-count weighting V(lambda), "
            "or auto: energy when a spectral correction file is supplied, otherwise photon."
        ),
    )
    parser.add_argument(
        "--spectral-correction-file",
        type=Path,
        help="Optional wavelength correction CSV with wavelength and correction_factor columns.",
    )
    parser.add_argument(
        "--no-subtract-dark",
        action="store_true",
        help="Do not subtract the saved black-screen baseline spectrum.",
    )
    parser.add_argument(
        "--clip-negative",
        action="store_true",
        help="Clip negative values after dark subtraction before integration.",
    )
    parser.add_argument("--out", type=Path, help="Optional CSV output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    subtract_dark = not args.no_subtract_dark
    spectral_correction = (
        load_spectral_correction(args.spectral_correction_file) if args.spectral_correction_file else None
    )
    count_basis = args.count_basis
    if count_basis == "auto":
        count_basis = "energy" if spectral_correction is not None else "photon"

    reference = load_calibration(args.reference)
    reference_index, reference_drive = luminance_index(
        calibration=reference,
        colour=args.reference_colour,
        requested_drive=args.drive,
        count_basis=count_basis,
        subtract_dark=subtract_dark,
        clip_negative=args.clip_negative,
        spectral_correction=spectral_correction,
    )
    if reference_index <= 0:
        raise ValueError(f"Reference luminance index must be positive, got {reference_index}")

    scale = args.reference_luminance_cd_m2 / reference_index
    print(
        "Reference:",
        f"{args.reference} {args.reference_colour} drive={reference_drive:g}",
        f"index={reference_index:.9g}",
        f"scale={scale:.9g} cd/m^2 per index",
        f"basis={count_basis}",
    )
    if spectral_correction is not None:
        print(f"Spectral correction: {spectral_correction.path}")

    rows: list[dict[str, object]] = []
    generated_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    for target_file in expand_targets(args.targets):
        calibration = load_calibration(target_file)
        for colour in args.colours:
            target_index, actual_drive = luminance_index(
                calibration=calibration,
                colour=colour,
                requested_drive=args.drive,
                count_basis=count_basis,
                subtract_dark=subtract_dark,
                clip_negative=args.clip_negative,
                spectral_correction=spectral_correction,
            )
            rows.append(
                {
                    "generated_at": generated_at,
                    "target_file": str(target_file),
                    "target_timestamp": calibration.timestamp,
                    "colour": colour,
                    "requested_drive": args.drive,
                    "actual_drive": actual_drive,
                    "integration_us": calibration.integration_us,
                    "luminance_index": target_index,
                    "estimated_luminance_cd_m2": target_index * scale,
                    "reference_file": str(args.reference),
                    "reference_colour": args.reference_colour,
                    "reference_drive": reference_drive,
                    "reference_luminance_cd_m2": args.reference_luminance_cd_m2,
                    "reference_luminance_index": reference_index,
                    "scale_cd_m2_per_index": scale,
                    "count_basis": count_basis,
                    "dark_subtracted": subtract_dark,
                    "negative_values_clipped": args.clip_negative,
                    "spectral_correction_file": "" if spectral_correction is None else str(spectral_correction.path),
                }
            )

    print_rows(rows)
    if args.out:
        write_csv(args.out, rows)
        print(f"Saved luminance estimates to {args.out.resolve()}")


if __name__ == "__main__":
    main()
