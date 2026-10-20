# HOWTO: calibrate a monitor from scratch

A start-to-finish walkthrough for someone who has never used this toolbox. By the
end you will have a PsychoPy monitor profile you can load by name in your
experiments. Follow it top to bottom the first time; skip the optional sections
once you know what you need.

If a term is unfamiliar, the [Key concepts](README.md#key-concepts) section of the
README explains gamma, spectra, fibre correction, and absolute anchoring.

---

## 0. Before you start — a checklist

You need, at minimum:

- [ ] An Ocean Optics spectrometer plugged in over USB.
- [ ] The monitor you want to calibrate, connected and on.
- [ ] A dark room (stray light corrupts the measurement).
- [ ] Python 3.10 or 3.11 and [`uv`](https://docs.astral.sh/uv/) installed.

Optional but recommended for a full calibration:

- [ ] A photometer (e.g. Minolta LS-110) for absolute cd/m² anchoring.
- [ ] Your calibration lamp + the fibre/light-pipe, if you measure through one.

Mount the spectrometer so it looks squarely at a patch near the centre of the
screen, close enough to fill its field of view, and don't move it once you start.

**Turn off OS colour management before you measure.** Desktop colour management
(GNOME/`colord`, macOS ColorSync, Night Light / f.lux and similar) can install a
colour-correction *matrix* on the GPU, between your stimulus and the panel. This
silently invalidates a calibration, and it hides well: these matrices normally
preserve white, so a white-point check looks perfect while the pure primaries are
wrong. The symptom to watch for is a display that measures as non-additive —
W noticeably different from R+G+B in some band — which real LCD/LED panels
usually are not. On Linux/NVIDIA you can check with
`xrandr --prop | grep CscMatrix` (identity is `65536 0 0 / 0 65536 0 / 0 0 65536`).

---

## 1. Set up the environment (once)

```bash
git clone https://github.com/wadelab/oceanoptics-public.git
cd oceanoptics-public

uv venv
source .venv/bin/activate
uv sync
uv sync --extra psychopy      # needed for anything that puts colours on screen
```

**Linux note:** `uv sync --extra psychopy` can fail while building wxPython from
source (`No space left on device` is the usual symptom) — PyPI ships no Linux
wxPython wheel, and the pinned 4.2.5 has to be compiled. PsychoPy only needs
`wxPython>=4.1.1`, so install a prebuilt wheel instead and constrain PsychoPy to
it (seconds, not a multi-gigabyte build):

```bash
uv pip install "wxPython==4.2.2" --no-build \
  --find-links https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-22.04/
echo "wxPython==4.2.2" > constraints.txt
uv pip install "psychopy>=2024.2,<2026" -c constraints.txt
```

Swap `ubuntu-22.04` for your own distro directory; only some versions are built.

**Linux only:** if the next step reports a USB permission error, add a udev rule
(see [Troubleshooting](README.md#troubleshooting)) and replug the spectrometer
before continuing.

**Checkpoint:** `python -c "import seabreeze; seabreeze.use('pyseabreeze'); from seabreeze.spectrometers import list_devices; print(list_devices())"`
should print your spectrometer, not an empty list.

---

## 2. Measure the screen (required)

This is the core measurement: each colour gun's spectrum and gamma curve.

```bash
python calibrate_screen.py \
  --levels 16 --int_us 100000 \
  --screen 0 --windowed \
  --out calibration_data/run_first
```

What the flags mean:

- `--levels 16` — number of drive levels per gun (more = finer gamma curve, slower).
- `--int_us 100000` — spectrometer integration time in microseconds. If spectra
  look flat/noisy, raise it; if they saturate (clipped flat top), lower it.
- `--screen 0` — display index (`0` = primary, `1` = second monitor, …).
- `--windowed` — run in a window; use `--fullscr` for a proper calibration.
- `--out …` — output directory; use a fresh, descriptive name per run.

A window opens and steps through coloured fields while the spectrometer reads each
one. Sit still and keep the room dark.

**What you get** in `calibration_data/run_first/`:

- `spectra_*.csv`, `spectra_final_*.csv` — measured spectra per gun/level.
- `gamma_curve_*.csv/.png`, `gamma_params_*.csv` — the transfer functions.
- `calibration_*.npz` — everything bundled, plus metadata.
- `run_summary_*.txt` — human-readable settings (screen size, refresh, backend, …).

**Checkpoint:** open `gamma_curve_*.png`. You should see smooth, monotonically
rising curves for R, G, B. Ragged or flat curves usually mean stray light, a
moved sensor, or a wrong integration time — fix and re-measure before continuing.

> **Minimal path:** if you don't need fibre correction or absolute luminance, jump
> to [step 6](#6-build-the-psychopy-monitor-profile-required) now.

---

## 3. (Optional) Take absolute luminance readings

The spectrometer measures *relative* light. To get real cd/m², take one or more
photometer readings. Show the fields:

```bash
python measure_luminance.py --outdir calibration_data/luminance_first
```

Point the photometer at each field (black, mid-gray, white), note the reading,
and enter it when prompted — or pass them directly if you already have them:

```bash
python measure_luminance.py \
  --black-cd-m2 0.12 --mid-cd-m2 85.4 --white-cd-m2 210.7 \
  --outdir calibration_data/luminance_first
```

Readings are saved as CSV and JSON.

---

## 4. (Optional) Measure the fibre / light-pipe

Skip this unless you view the screen through a fibre or light-pipe (common on
MEG/MRI/EEG rigs). A long fibre dims some wavelengths more than others; this step
measures that so step 6 can correct for it.

Measure the calibration lamp through the **same** fibre path you used for the
screen:

```bash
python measure_fibre.py \
  --outdir calibration_data/lamp_first \
  --prefix lamp_measurement \
  --n-spectra 10 --integration-us 10000 \
  --lamp-file data/LampFiles/030410313_FIB.LMP \
  --correction-out calibration_data/lamp_first/correction_factors.csv
```

**You will be asked which fibre this is.** A correction curve only applies to the
fibre it was measured through, so the script prompts for an identifier and
refuses to record an anonymous one:

```
Which fibre / light-pipe is this measurement going through?
  Use something you will recognise later (e.g. MRI_long_plastic, blue_SN12345).
Fibre identifier:
```

Use something durable — the serial number if the fibre has one, otherwise where
it lives and what it is (`MRI_long_plastic`). The identifier goes into the output
filenames, into a `fibre_<id>_<timestamp>.json` metadata file, and into a
`fibre_id` column in `correction_factors.csv`, so a correction can always be
traced back to its fibre. Pass `--fibre <id>` to skip the prompt when scripting.

`--lamp-file` is the lamp's known reference spectrum. Two vendor HL-2000-CAL files
ship in [`data/LampFiles/`](data/LampFiles/); use the one matching your fibre/optic
setup, or your own lamp's reference file.

**What you get:** `correction_factors.csv` with columns
`wavelength,correction_factor,fibre_id`, plus a `fibre_*.json` noting the fibre
and acquisition settings. (Older two-column correction files still work.)

---

## 5. (Optional) Estimate luminance for other screens

If you calibrated several screens through the same optical path but only took a
photometer reading on one of them, reuse that reading as a reference:

```bash
uv run python estimate_luminance.py \
  --reference calibration_data/run_first/calibration_YYYYMMDD_HHMMSS.npz \
  --reference-luminance-cd-m2 84 \
  --out calibration_data/luminance_estimates.csv \
  calibration_data/run_second calibration_data/run_third
```

Add `--colours R,G,B,W` to estimate each gun's maximum as well as full white.

---

## 6. Build the PsychoPy monitor profile (required)

Turn the measurements into a profile PsychoPy can use. Fill in the real timestamped
filenames from step 2 (and step 4 if you did fibre correction).

**With fibre correction:**

```bash
python combine_calibrations.py \
  --spectra-file  calibration_data/run_first/spectra_final_YYYYMMDD_HHMMSS.csv \
  --correction-file calibration_data/lamp_first/correction_factors.csv \
  --gamma-params  calibration_data/run_first/gamma_params_YYYYMMDD_HHMMSS.csv \
  --monitor-name  MyMonitor \
  --width-cm 50 --distance-cm 60 --size-pix 1920 1080
```

**Without fibre correction** — just omit `--correction-file`.

Not sure of the exact filenames? Run it interactively and click through pickers:

```bash
python combine_calibrations.py --gui
```

For very dim / ND-filtered runs where the signal is close to the black baseline,
add `--subtract-dark` to remove the saved dark spectrum first.

**What you get:**

- `*_corrected.csv` — the fibre-corrected spectra.
- a diagnostic PNG.
- a PsychoPy monitor `.json` (when `--monitor-name` is set).

**Checkpoint:** confirm the profile loads. In Python:

```python
from psychopy import monitors
m = monitors.Monitor("MyMonitor")
print(m.getSizePix(), m.getWidth(), m.getGammaGrid())
```

You can also inspect it with the archived helper:

```bash
python archived_scripts/psychopy_monitorDiagnostic.py MyMonitor
```

---

## 7. Use it

In an experiment, ask PsychoPy for the monitor by name:

```python
from psychopy import monitors, visual
mon = monitors.Monitor("MyMonitor")
win = visual.Window(monitor=mon, units="deg", fullscr=True)
```

PsychoPy now applies your measured gamma linearisation, and your saved spectra are
available for cone/receptor calculations.

---

## When things look wrong

| Symptom | Likely cause / fix |
| --- | --- |
| Spectrometer not found | USB permissions (Linux udev rule); try `--backend pyseabreeze`. |
| Read hangs | Switch away from `cseabreeze` to `--backend pyseabreeze`. |
| Flat/noisy spectra | Integration time too low, or room not dark. Raise `--int_us`. |
| Clipped (flat-topped) spectra | Integration time too high — lower `--int_us`. |
| Ragged gamma curve | Sensor moved, stray light, or reflections. Re-measure. |
| Can't set gamma LUT | Add `--native_gamma` to the measurement scripts. |
| Display measures as non-additive (W != R+G+B) | OS colour management is applying a GPU colour matrix. Disable it (see [step 0](#0-before-you-start--a-checklist)) and re-measure. |
| `No space left on device` during setup | wxPython is building from source; use the prebuilt wheel (see [step 1](#1-set-up-the-environment-once)). |
| One `[Errno 75] Overflow` at the start of a run | Expected on USB2000: the first read after the device opens always fails. The retry logic absorbs it; ignore it. |
| Measured refresh rate is ~1 Hz | No display is actually connected (check `xrandr`). A powered-off monitor reports as disconnected and there is no vblank to sync to. |

More detail in [README.md](README.md#troubleshooting).
