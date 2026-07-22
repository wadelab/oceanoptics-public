#!/usr/bin/env python3
"""Combine screen and fibre calibrations into corrected spectra and monitor profiles."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def apply_correction(
    spectra_file: Path,
    correction_file: Path,
    output_file: Path,
    start_nm: float,
    stop_nm: float,
    step_nm: float,
    plot_file: Path | None,
    calibration_file: Path | None = None,
    subtract_dark: bool = False,
    clip_negative: bool = True,
) -> pd.DataFrame:
    screen_df = pd.read_csv(spectra_file)
    corr_df = pd.read_csv(correction_file)

    wavelength_col = "wavelength_nm" if "wavelength_nm" in screen_df.columns else "wavelength"
    required = {wavelength_col, "R", "G", "B"}
    if not required.issubset(screen_df.columns):
        raise ValueError(f"{spectra_file} must contain {sorted(required)}")
    if not {"wavelength", "correction_factor"}.issubset(corr_df.columns):
        raise ValueError(f"{correction_file} must contain wavelength and correction_factor columns")

    wavelengths = np.arange(start_nm, stop_nm + step_nm, step_nm)
    corrected = pd.DataFrame({"wavelength": wavelengths})

    if subtract_dark:
        if calibration_file is None:
            calibration_file = _find_calibration_for_spectra(spectra_file)
        rgb = load_dark_subtracted_rgb(calibration_file, wavelengths)
        if clip_negative:
            rgb = np.maximum(rgb, 0.0)
        corrected[["R", "G", "B"]] = rgb
    else:
        for col in ["R", "G", "B"]:
            corrected[col] = np.interp(wavelengths, screen_df[wavelength_col], screen_df[col])

        min_val = corrected[["R", "G", "B"]].values.min()
        corrected[["R", "G", "B"]] = corrected[["R", "G", "B"]] - min_val

    max_val = corrected[["R", "G", "B"]].values.max()
    if max_val == 0:
        raise ValueError("Cannot normalize a flat/zero RGB spectrum.")
    corrected[["R", "G", "B"]] = corrected[["R", "G", "B"]] / max_val

    corr_interp = np.interp(wavelengths, corr_df["wavelength"], corr_df["correction_factor"])
    corrected["correction_factor"] = corr_interp

    for col in ["R", "G", "B"]:
        corrected[f"{col}_corrected"] = corrected[col] * corr_interp

    max_corrected = corrected[[f"{col}_corrected" for col in ["R", "G", "B"]]].values.max()
    if max_corrected == 0:
        raise ValueError("Cannot normalize corrected spectra; all corrected values are zero.")
    for col in ["R", "G", "B"]:
        corrected[f"{col}_corrected"] = corrected[f"{col}_corrected"] / max_corrected

    output_file.parent.mkdir(parents=True, exist_ok=True)
    corrected.to_csv(output_file, index=False)

    if plot_file:
        plot_file.parent.mkdir(parents=True, exist_ok=True)
        fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        for col, color in [("R", "red"), ("G", "green"), ("B", "blue")]:
            axes[0].plot(wavelengths, corrected[col], color=color, linestyle="-", label=f"{col} original")
            axes[0].plot(
                wavelengths,
                corrected[f"{col}_corrected"],
                color=color,
                linestyle="--",
                label=f"{col} corrected",
            )
        axes[0].set_ylabel("Normalized intensity")
        axes[0].set_title("Original vs Corrected Monitor Spectra")
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(ncol=2, fontsize=8)

        axes[1].plot(wavelengths, corr_interp, color="black")
        axes[1].set_xlabel("Wavelength (nm)")
        axes[1].set_ylabel("Correction factor")
        axes[1].set_title("Applied Correction Factor")
        axes[1].grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(plot_file, dpi=160)
        plt.close(fig)

    return corrected


def _find_calibration_for_spectra(spectra_file: Path) -> Path:
    timestamp = spectra_file.stem.removeprefix("spectra_final_")
    calibration_file = spectra_file.with_name(f"calibration_{timestamp}.npz")
    if not calibration_file.exists():
        raise FileNotFoundError(
            f"Could not infer calibration NPZ for {spectra_file}; expected {calibration_file}. "
            "Pass --calibration-file explicitly."
        )
    return calibration_file


def load_dark_subtracted_rgb(calibration_file: Path, wavelengths: np.ndarray) -> np.ndarray:
    data = np.load(calibration_file, allow_pickle=True)
    required = {"wavelengths", "drive_levels", "spectra", "dark"}
    missing = required.difference(data.files)
    if missing:
        raise ValueError(f"{calibration_file} is missing required NPZ entries: {sorted(missing)}")

    source_wavelengths = np.asarray(data["wavelengths"], dtype=float)
    drive_levels = np.asarray(data["drive_levels"], dtype=float)
    spectra = data["spectra"].item()
    dark = np.asarray(data["dark"], dtype=float)
    max_drive_index = int(np.argmin(np.abs(drive_levels - 1.0)))

    rgb = np.empty((wavelengths.size, 3), dtype=float)
    for i, colour in enumerate(["R", "G", "B"]):
        if colour not in spectra:
            raise ValueError(f"{calibration_file} has no {colour!r} spectra")
        signal = np.asarray(spectra[colour][max_drive_index], dtype=float) - dark
        rgb[:, i] = np.interp(wavelengths, source_wavelengths, signal)
    return rgb


def load_gamma_params(path: Path) -> list[float]:
    df = pd.read_csv(path)
    gamma_map = {row["colour"].strip().upper(): float(row["gamma"]) for _, row in df.iterrows()}
    return [gamma_map[colour] for colour in ("R", "G", "B")]


def create_monitor_profile(
    corrected_file: Path,
    gamma_params_file: Path,
    monitor_name: str,
    width_cm: float,
    distance_cm: float,
    size_pix: tuple[int, int],
) -> Path:
    from scipy.interpolate import interp1d
    from psychopy import __version__ as psychopy_version
    from psychopy.monitors import Monitor
    from psychopy.monitors.calibTools import makeDKL2RGB, makeLMS2RGB

    df = pd.read_csv(corrected_file)
    nm = df["wavelength"].to_numpy()
    rgb = df[["R_corrected", "G_corrected", "B_corrected"]].to_numpy()

    valid = (nm >= 380) & (nm <= 720)
    nm = nm[valid]
    rgb = rgb[valid]

    new_nm = np.arange(380, 721, 1)
    rgb_resampled = interp1d(nm, rgb, axis=0, kind="linear", fill_value="extrapolate")(new_nm)
    rgb_resampled = np.nan_to_num(rgb_resampled, nan=0.0)
    rgb_resampled /= np.max(rgb_resampled, axis=0)

    mon = Monitor(name=monitor_name, width=width_cm, distance=distance_cm)
    mon.setSizePix(size_pix)
    mon.setSpectra(new_nm, rgb_resampled.T)
    mon.setLMS_RGB(makeLMS2RGB(new_nm, rgb_resampled.T))
    mon.setDKL_RGB(makeDKL2RGB(new_nm, rgb_resampled.T))
    mon.setGamma(np.asarray(load_gamma_params(gamma_params_file), float))
    mon.setLineariseMethod(0)
    mon.setPsychopyVersion(psychopy_version)
    mon.save()
    return Path.home() / ".psychopy3" / "monitors" / f"{monitor_name}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply fibre correction to screen spectra and optionally generate a PsychoPy monitor profile."
    )
    parser.add_argument("--gui", action="store_true", help="Choose input files with a simple Tk file picker.")
    parser.add_argument("--spectra-file", type=Path, help="Raw spectra_final_*.csv file.")
    parser.add_argument("--correction-file", type=Path, help="correction_factors.csv file.")
    parser.add_argument("--calibration-file", type=Path,
                        help="calibration_*.npz file used for dark subtraction. Defaults to sibling file matching spectra timestamp.")
    parser.add_argument("--out", type=Path, help="Output corrected spectra CSV.")
    parser.add_argument("--plot", type=Path, help="Optional diagnostic plot path.")
    parser.add_argument("--start-nm", type=float, default=380, help="First output wavelength.")
    parser.add_argument("--stop-nm", type=float, default=740, help="Last output wavelength.")
    parser.add_argument("--step-nm", type=float, default=5, help="Output wavelength step.")
    parser.add_argument("--subtract-dark", action="store_true",
                        help="Subtract the saved dark spectrum from calibration_*.npz before correction.")
    parser.add_argument("--keep-negative", action="store_true",
                        help="Keep negative values after dark subtraction instead of clipping them to zero.")
    parser.add_argument("--gamma-params", type=Path, help="gamma_params_*.csv from calibrate_screen.py.")
    parser.add_argument("--monitor-name", help="If set, create this PsychoPy monitor profile.")
    parser.add_argument("--width-cm", type=float, default=50.0, help="Screen width for monitor profile.")
    parser.add_argument("--distance-cm", type=float, default=60.0, help="Viewing distance for monitor profile.")
    parser.add_argument("--size-pix", type=int, nargs=2, metavar=("W", "H"), default=(1920, 1080))
    return parser.parse_args()


def _find_neighbor(path: Path | None, pattern: str) -> Path | None:
    if path is None:
        return None
    matches = sorted(path.parent.glob(pattern))
    return matches[-1] if matches else None


def run_gui(args: argparse.Namespace) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    root = tk.Tk()
    root.title("Combine Screen and Fibre Calibrations")
    root.geometry("1120x760")

    spectra_var = tk.StringVar(value=str(args.spectra_file or ""))
    correction_var = tk.StringVar(value=str(args.correction_file or ""))
    gamma_var = tk.StringVar(value=str(args.gamma_params or ""))
    output_var = tk.StringVar(value=str(args.out or ""))
    monitor_var = tk.StringVar(value=args.monitor_name or "")
    width_var = tk.StringVar(value=str(args.width_cm))
    distance_var = tk.StringVar(value=str(args.distance_cm))
    size_w_var = tk.StringVar(value=str(args.size_pix[0]))
    size_h_var = tk.StringVar(value=str(args.size_pix[1]))
    status_var = tk.StringVar(value="Choose files, then preview or combine.")

    main = ttk.Frame(root, padding=10)
    main.pack(fill=tk.BOTH, expand=True)

    controls = ttk.Frame(main)
    controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    controls.columnconfigure(1, weight=1)

    def add_file_row(row: int, label: str, var: tk.StringVar, title: str) -> None:
        ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=var, width=46).grid(row=row, column=1, sticky="ew", pady=3)

        def browse() -> None:
            path = filedialog.askopenfilename(title=title, filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
            if path:
                var.set(path)
                if var is spectra_var:
                    gamma = _find_neighbor(Path(path), "gamma_params_*.csv")
                    if gamma and not gamma_var.get():
                        gamma_var.set(str(gamma))
                    if not output_var.get():
                        spectra_path = Path(path)
                        output_var.set(str(spectra_path.with_name(f"{spectra_path.stem}_corrected.csv")))

        ttk.Button(controls, text="Browse", command=browse).grid(row=row, column=2, padx=(5, 0), pady=3)

    add_file_row(0, "Screen spectra", spectra_var, "Select spectra_final CSV")
    add_file_row(1, "Fibre correction", correction_var, "Select correction_factors CSV")
    add_file_row(2, "Gamma params", gamma_var, "Select gamma_params CSV")

    ttk.Label(controls, text="Output CSV").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(controls, textvariable=output_var, width=46).grid(row=3, column=1, sticky="ew", pady=3)
    ttk.Button(
        controls,
        text="Browse",
        command=lambda: output_var.set(
            filedialog.asksaveasfilename(
                title="Save corrected spectra",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
            )
            or output_var.get()
        ),
    ).grid(row=3, column=2, padx=(5, 0), pady=3)

    ttk.Separator(controls).grid(row=4, column=0, columnspan=3, sticky="ew", pady=12)
    ttk.Label(controls, text="Monitor name").grid(row=5, column=0, sticky="w", pady=3)
    ttk.Entry(controls, textvariable=monitor_var, width=46).grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)
    ttk.Label(controls, text="Width cm").grid(row=6, column=0, sticky="w", pady=3)
    ttk.Entry(controls, textvariable=width_var, width=12).grid(row=6, column=1, sticky="w", pady=3)
    ttk.Label(controls, text="Distance cm").grid(row=7, column=0, sticky="w", pady=3)
    ttk.Entry(controls, textvariable=distance_var, width=12).grid(row=7, column=1, sticky="w", pady=3)
    ttk.Label(controls, text="Size px").grid(row=8, column=0, sticky="w", pady=3)
    size_frame = ttk.Frame(controls)
    size_frame.grid(row=8, column=1, sticky="w", pady=3)
    ttk.Entry(size_frame, textvariable=size_w_var, width=8).pack(side=tk.LEFT)
    ttk.Label(size_frame, text=" x ").pack(side=tk.LEFT)
    ttk.Entry(size_frame, textvariable=size_h_var, width=8).pack(side=tk.LEFT)

    tabs = ttk.Notebook(main)
    tabs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    canvases: dict[str, FigureCanvasTkAgg] = {}
    axes: dict[str, object] = {}
    for name in ["Screen Spectra", "Gamma", "Corrected"]:
        tab = ttk.Frame(tabs)
        tabs.add(tab, text=name)
        fig = Figure(figsize=(7.2, 5.2), dpi=100)
        ax = fig.add_subplot(111)
        ax.set_title(name)
        ax.grid(True, alpha=0.25)
        canvas = FigureCanvasTkAgg(fig, master=tab)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvases[name] = canvas
        axes[name] = ax

    def plot_screen() -> None:
        spectra_path = Path(spectra_var.get())
        df = pd.read_csv(spectra_path)
        wavelength_col = "wavelength_nm" if "wavelength_nm" in df.columns else "wavelength"
        ax = axes["Screen Spectra"]
        ax.clear()
        for col, color in [("R", "red"), ("G", "green"), ("B", "blue")]:
            ax.plot(df[wavelength_col], df[col], color=color, label=col)
        ax.set_title("Screen Spectra at Maximum Drive")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Intensity")
        ax.grid(True, alpha=0.25)
        ax.legend()
        canvases["Screen Spectra"].draw()

    def plot_gamma() -> None:
        gamma_path = Path(gamma_var.get()) if gamma_var.get() else None
        if gamma_path is None or not gamma_path.exists():
            gamma_path = _find_neighbor(Path(spectra_var.get()), "gamma_params_*.csv")
            if gamma_path:
                gamma_var.set(str(gamma_path))
        curve_path = _find_neighbor(gamma_path, "gamma_curve_*.csv") if gamma_path else None
        ax = axes["Gamma"]
        ax.clear()
        if curve_path and curve_path.exists():
            curve = pd.read_csv(curve_path)
            for col, color in [("R", "red"), ("G", "green"), ("B", "blue"), ("W", "black")]:
                if col in curve:
                    ax.plot(curve["drive"], curve[col], "o-", color=color, label=col)
            ax.set_title("Measured Gamma Curves")
            ax.set_xlabel("Drive")
            ax.set_ylabel("Mean intensity")
            ax.legend()
        elif gamma_path and gamma_path.exists():
            params = pd.read_csv(gamma_path)
            ax.bar(params["colour"], params["gamma"], color=["red", "green", "blue", "gray"][: len(params)])
            ax.set_title("Fitted Gamma Values")
            ax.set_ylabel("Gamma")
        else:
            ax.text(0.5, 0.5, "No gamma file selected", ha="center", va="center")
        ax.grid(True, alpha=0.25)
        canvases["Gamma"].draw()

    def plot_corrected(corrected: pd.DataFrame) -> None:
        ax = axes["Corrected"]
        ax.clear()
        for col, color in [("R", "red"), ("G", "green"), ("B", "blue")]:
            ax.plot(corrected["wavelength"], corrected[col], color=color, alpha=0.35, linestyle="-")
            ax.plot(corrected["wavelength"], corrected[f"{col}_corrected"], color=color, linestyle="--", label=f"{col} corrected")
        ax.set_title("Corrected Spectra")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Normalized intensity")
        ax.grid(True, alpha=0.25)
        ax.legend()
        canvases["Corrected"].draw()

    def preview() -> None:
        try:
            plot_screen()
            plot_gamma()
            status_var.set("Preview updated.")
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))

    def combine() -> None:
        try:
            spectra_path = Path(spectra_var.get())
            correction_path = Path(correction_var.get())
            output_path = Path(output_var.get()) if output_var.get() else spectra_path.with_name(f"{spectra_path.stem}_corrected.csv")
            output_var.set(str(output_path))
            corrected = apply_correction(
                spectra_file=spectra_path,
                correction_file=correction_path,
                output_file=output_path,
                start_nm=args.start_nm,
                stop_nm=args.stop_nm,
                step_nm=args.step_nm,
                plot_file=output_path.with_suffix(".png"),
                calibration_file=args.calibration_file,
                subtract_dark=args.subtract_dark,
                clip_negative=not args.keep_negative,
            )
            plot_corrected(corrected)
            profile_msg = ""
            if monitor_var.get():
                if not gamma_var.get():
                    raise ValueError("Gamma params are required to create a monitor profile.")
                profile = create_monitor_profile(
                    corrected_file=output_path,
                    gamma_params_file=Path(gamma_var.get()),
                    monitor_name=monitor_var.get(),
                    width_cm=float(width_var.get()),
                    distance_cm=float(distance_var.get()),
                    size_pix=(int(size_w_var.get()), int(size_h_var.get())),
                )
                profile_msg = f" Monitor profile: {profile}"
            status_var.set(f"Saved corrected spectra: {output_path}.{profile_msg}")
            messagebox.showinfo("Complete", status_var.get())
        except Exception as exc:
            messagebox.showerror("Combine failed", str(exc))

    button_row = ttk.Frame(controls)
    button_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(14, 6))
    ttk.Button(button_row, text="Preview", command=preview).pack(side=tk.LEFT)
    ttk.Button(button_row, text="Combine", command=combine).pack(side=tk.LEFT, padx=8)
    ttk.Button(button_row, text="Quit", command=root.destroy).pack(side=tk.LEFT)
    ttk.Label(controls, textvariable=status_var, wraplength=420).grid(row=10, column=0, columnspan=3, sticky="ew", pady=6)

    if spectra_var.get():
        preview()
    root.mainloop()


if __name__ == "__main__":
    args = parse_args()
    if args.gui:
        run_gui(args)
        raise SystemExit(0)
    if not args.spectra_file or not args.correction_file:
        raise SystemExit("--spectra-file and --correction-file are required unless selected with --gui")
    output = args.out
    if output is None:
        output = args.spectra_file.with_name(f"{args.spectra_file.stem}_corrected.csv")
    plot = args.plot
    if plot is None:
        plot = output.with_suffix(".png")
    corrected = apply_correction(
        spectra_file=args.spectra_file,
        correction_file=args.correction_file,
        output_file=output,
        start_nm=args.start_nm,
        stop_nm=args.stop_nm,
        step_nm=args.step_nm,
        plot_file=plot,
        calibration_file=args.calibration_file,
        subtract_dark=args.subtract_dark,
        clip_negative=not args.keep_negative,
    )
    print(f"Saved {len(corrected)} corrected spectra rows to {output}")
    print(f"Saved diagnostic plot to {plot}")
    if args.monitor_name:
        if not args.gamma_params:
            raise SystemExit("--gamma-params is required when --monitor-name is used")
        profile = create_monitor_profile(
            corrected_file=output,
            gamma_params_file=args.gamma_params,
            monitor_name=args.monitor_name,
            width_cm=args.width_cm,
            distance_cm=args.distance_cm,
            size_pix=tuple(args.size_pix),
        )
        print(f"Saved PsychoPy monitor profile to {profile}")
