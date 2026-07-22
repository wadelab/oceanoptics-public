"""
measure_luminance.py
--------------------

Manual Minolta luminance measurement helper.

Shows black, mid-gray, and full-white PsychoPy screens. Each screen remains up
until a key is pressed in the PsychoPy window. Minolta cd/m^2 readings can be
provided as command-line arguments or entered at the terminal when prompted.
Results are saved as CSV and JSON in a timestamped output directory.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

GAMMA_ERROR_POLICY = "raise"


def generate_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_optional_float(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a numeric cd/m^2 value, got {value!r}") from exc


def prompt_for_reading(label: str) -> float:
    while True:
        raw = input(f"Enter Minolta luminance for {label} in cd/m^2: ").strip()
        try:
            return float(raw)
        except ValueError:
            print("Please enter a numeric value, for example 123.45")


def save_results(
    outdir: Path,
    timestamp: str,
    rows: list[dict[str, float | str | tuple[float, float, float]]],
    meta: dict[str, object],
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    csv_path = outdir / f"luminance_{timestamp}.csv"
    with open(csv_path, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["condition", "drive_level", "psychopy_rgb", "luminance_cd_m2"])
        for row in rows:
            rgb = row["psychopy_rgb"]
            writer.writerow([
                row["condition"],
                row["drive_level"],
                " ".join(str(v) for v in rgb),
                row["luminance_cd_m2"],
            ])

    json_path = outdir / f"luminance_{timestamp}.json"
    with open(json_path, "w") as file:
        json.dump(
            {
                "timestamp": timestamp,
                "meta": meta,
                "measurements": rows,
            },
            file,
            indent=2,
        )

    print(f"Saved luminance CSV to {csv_path.resolve()}")
    print(f"Saved luminance JSON to {json_path.resolve()}")


def main(
    outdir: str | Path | None,
    black_cd_m2: float | None,
    mid_cd_m2: float | None,
    white_cd_m2: float | None,
    identity_gamma: bool = True,
    screen: int = 0,
    fullscr: bool = False,
) -> None:
    from psychopy import core, event, visual

    timestamp = generate_timestamp()
    output_dir = Path(outdir) if outdir else Path("calibration_data") / f"luminance_{timestamp}"

    win_gamma = 1.0 if identity_gamma else None
    requested_window_size = (1000, 800)

    def open_window() -> visual.Window:
        window = visual.Window(
            size=requested_window_size,
            color=(-1, -1, -1),
            units="pix",
            fullscr=fullscr,
            allowGUI=True,
            gamma=win_gamma,
            gammaErrorPolicy=GAMMA_ERROR_POLICY,
            screen=screen,
        )
        core.wait(0.5)
        return window

    def close_window() -> None:
        nonlocal win
        if win is not None:
            win.close()
            win = None

    print(
        "Luminance window gamma:",
        "identity LUT requested (gamma=1.0)" if identity_gamma else "native OS/GPU LUT",
    )
    print("Luminance window mode:", "fullscreen" if fullscr else "windowed")
    print("Luminance target screen index:", screen)

    requested = [
        {
            "condition": "black",
            "drive_level": 0.0,
            "psychopy_rgb": (-1.0, -1.0, -1.0),
            "luminance_cd_m2": black_cd_m2,
        },
        {
            "condition": "mid_gray",
            "drive_level": 0.5,
            "psychopy_rgb": (0.0, 0.0, 0.0),
            "luminance_cd_m2": mid_cd_m2,
        },
        {
            "condition": "white",
            "drive_level": 1.0,
            "psychopy_rgb": (1.0, 1.0, 1.0),
            "luminance_cd_m2": white_cd_m2,
        },
    ]

    win = open_window()
    try:
        for row in requested:
            condition = row["condition"]
            if win is None:
                win = open_window()
            win.color = row["psychopy_rgb"]
            win.flip()
            win.flip()
            event.clearEvents(eventType="keyboard")
            print(f"Showing {condition}; take Minolta reading, then press any key in the PsychoPy window.")
            event.waitKeys()

            if row["luminance_cd_m2"] is None:
                close_window()
                row["luminance_cd_m2"] = prompt_for_reading(condition)
    finally:
        close_window()

    save_results(
        output_dir,
        timestamp,
        requested,
        {
            "screen_index": screen,
            "window_mode": "fullscreen" if fullscr else "windowed",
            "requested_window_size_pix": f"{requested_window_size[0]} x {requested_window_size[1]}",
            "identity_gamma_requested": identity_gamma,
            "window_gamma": win_gamma,
            "gamma_error_policy": GAMMA_ERROR_POLICY,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual Minolta luminance measurement helper.")
    parser.add_argument("--outdir", type=str, default=None,
                        help="Output directory. Defaults to calibration_data/luminance_YYYYMMDD_HHMMSS.")
    parser.add_argument("--black-cd-m2", type=parse_optional_float, default=None,
                        help="Minolta reading for the black baseline screen in cd/m^2.")
    parser.add_argument("--mid-cd-m2", type=parse_optional_float, default=None,
                        help="Minolta reading for the mid-gray screen in cd/m^2.")
    parser.add_argument("--white-cd-m2", type=parse_optional_float, default=None,
                        help="Minolta reading for the full-white screen in cd/m^2.")
    parser.add_argument("--native_gamma", action="store_true",
                        help="Leave the OS/GPU gamma table untouched instead of requesting identity gamma.")
    parser.add_argument("--screen", type=int, default=0,
                        help="Display index for PsychoPy window (default: 0).")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--fullscr", action="store_true",
                            help="Run the luminance window in fullscreen mode.")
    mode_group.add_argument("--windowed", action="store_true",
                            help="Run the luminance window in windowed mode (default).")
    args = parser.parse_args()

    main(
        outdir=args.outdir,
        black_cd_m2=args.black_cd_m2,
        mid_cd_m2=args.mid_cd_m2,
        white_cd_m2=args.white_cd_m2,
        identity_gamma=not args.native_gamma,
        screen=args.screen,
        fullscr=args.fullscr,
    )
