# oceanoptics — display calibration with an Ocean Optics spectrometer

Tools for calibrating visual-display monitors with an [Ocean Optics](https://www.oceanoptics.com/)
spectrometer and turning the measurements into a ready-to-use
[PsychoPy](https://www.psychopy.org/) monitor profile. Written for vision-science
labs that need spectrally-correct, gamma-linearised stimuli (e.g. cone-isolating
or silent-substitution displays).

The pipeline measures each colour gun's spectrum and gamma transfer function,
optionally corrects for the wavelength-dependent transmission of a long fibre /
light-pipe, anchors the result to an absolute photometer reading, and writes a
PsychoPy `.json` monitor profile.

> **New here?** Start with **[HOWTO.md](HOWTO.md)** — a start-to-finish walkthrough
> that assumes no prior knowledge of the toolbox.

---

## What you need

**Hardware**

- An Ocean Optics spectrometer. A USB2000 (`USB2G15413`) is the reference device
  used to develop these scripts; other seabreeze-supported models should work.
- A computer driving the monitor you want to calibrate.
- *(Optional, for absolute luminance)* a photometer such as a Minolta LS-110.
- *(Optional, for fibre correction)* an Ocean Optics HL-2000-CAL calibration lamp
  and the fibre / light-pipe you use for your real measurements.

**Software**

- Python 3.10 or 3.11 (3.11 is the default; PsychoPy constrains the upper bound).
- [`uv`](https://docs.astral.sh/uv/) for environment and dependency management.
- PsychoPy (installed via the optional `psychopy` extra).
- `python-seabreeze` for talking to the spectrometer (pulled in as a dependency).

---

## Install

```bash
git clone https://github.com/wadelab/oceanoptics-public.git
cd oceanoptics-public

uv venv
source .venv/bin/activate
uv sync

# PsychoPy-based scripts (screen presentation) need the extra:
uv sync --extra psychopy
```

Notes:

- On **Linux**, older Ocean Optics USB devices need a udev rule before a
  non-root user can read them — see [Troubleshooting](#troubleshooting).
- On **macOS**, prefer a Python.org or uv-managed Python over the system Python
  for PsychoPy/wxPython.
- Two seabreeze backends exist: `pyseabreeze` (pure-Python, via PyUSB) and
  `cseabreeze` (the vendor C library). On the reference hardware `pyseabreeze`
  is reliable while `cseabreeze` sometimes hangs during a read, so `pyseabreeze`
  is the default.

---

## The five tools

The active workflow is deliberately kept to five root-level scripts. Every script
supports `--help`.

| Script | What it does |
| --- | --- |
| `calibrate_screen.py` | Measures each gun's (R/G/B/W) spectrum and gamma curve at a range of drive levels. The core measurement. |
| `measure_luminance.py` | Shows black / mid-gray / white fields so you can take manual photometer (cd/m²) readings. |
| `estimate_luminance.py` | Converts calibration spectra to cd/m² using one photometer-anchored reference spectrum. |
| `measure_fibre.py` | Measures the fibre / light-pipe path against a calibration lamp and builds wavelength correction factors. |
| `combine_calibrations.py` | Applies fibre correction to the screen spectra and writes the final PsychoPy monitor profile. |

Older, exploratory scripts and diagnostics live in [`archived_scripts/`](archived_scripts/)
and are kept for reference only.

---

## Before you measure: disable OS colour management

**Do this first. If you skip it your calibration can be silently wrong.**

Desktop colour management applies a colour-correction *matrix* on the GPU,
between your stimulus and the panel. Your software asks for pure red and the
monitor receives something else. It is especially nasty because these matrices
are built to preserve white, so a white-point check looks perfect while every
pure primary is wrong.

### Linux (GNOME / colord)

```bash
# 1. CHECK - identity means nothing is being applied
xrandr --prop | grep CscMatrix
#    identity is:  65536 0 0 0  0 65536 0 0  0 0 65536 0
#    anything else means a transform is ACTIVE

# 2. DISABLE for your account (survives package upgrades)
systemctl --user mask org.gnome.SettingsDaemon.Color.service
pkill -x gsd-color

# 3. DISABLE for every account on the machine (recommended on a shared rig)
sudo ln -sf /dev/null /etc/systemd/user/org.gnome.SettingsDaemon.Color.service

# 4. Remove stale auto-generated monitor profiles, and confirm Night Light is off
rm -f ~/.local/share/icc/edid-*.icc
gsettings get org.gnome.settings-daemon.plugins.color night-light-enabled   # want: false

# 5. Log out and back in, then re-run the check in step 1
```

The mask is **per user**: anyone else who logs in gets their own colour daemon
and their own corrupted data, which is why step 3 matters on a shared machine.

Note there is often **no software reset**: on NVIDIA's proprietary driver
`CscMatrix` is read-only and the xrandr `CTM` property is ignored, so you cannot
simply write an identity matrix back. Stopping the daemon is the fix.

### macOS

System Settings -> Displays -> Color Profile: choose a generic profile rather
than a calibrated/vendor one, and turn off **Night Shift** and **True Tone**.

### Windows

Settings -> Display -> **Night light** off; then Color Management -> Devices,
and remove any ICC profile associated with the display.

### Confirming it worked

The physical test is additivity: measure R, G, B and W separately and check
`W ~= R+G+B` in each band. A healthy display gives 0.99-1.01. On one rig a
GNOME-applied matrix drove red at 61% of its true value and produced a red-band
ratio of 2.73 while white still measured correctly.

---

## Typical workflow

A full, spectrally-corrected calibration is five steps. The minimal version is
just steps 1 and 5.

**Placeholders:** commands below use `YYYYMMDD_HHMMSS` as a stand-in for the
timestamps the scripts generate. No sample calibration outputs ship with this
repo — you generate your own into `calibration_data/`.

### 1. Measure the screen

```bash
python calibrate_screen.py \
  --levels 16 --int_us 100000 \
  --out calibration_data/run_YYYYMMDD_HHMMSS
```

Writes per-gun spectra, gamma curves/params, a `calibration_*.npz` bundle, and a
`run_summary_*.txt`. By default it requests an identity gamma LUT (`gamma=1.0`)
while measuring, so any existing monitor-profile gamma table does not distort the
measured display response. Use `--native_gamma` to measure with the OS/GPU gamma
table active instead.

Useful flags: `--screen N` (display index, `0` = primary), `--fullscr` /
`--windowed`, `--backend {pyseabreeze,cseabreeze,auto}`, `--settle_frames N`.

### 2. *(Optional)* Absolute luminance

Show fields for manual photometer readings:

```bash
python measure_luminance.py --outdir calibration_data/luminance_YYYYMMDD_HHMMSS
```

Or pass readings you already have:

```bash
python measure_luminance.py \
  --black-cd-m2 0.12 --mid-cd-m2 85.4 --white-cd-m2 210.7 \
  --outdir calibration_data/luminance_YYYYMMDD_HHMMSS
```

### 3. *(Optional)* Measure the fibre / light-pipe

Long fibres attenuate some wavelengths more than others. Measure the calibration
lamp through the *same* fibre path used for the screen, then derive correction
factors. Two vendor lamp reference files ship under [`data/LampFiles/`](data/LampFiles/):

```bash
python measure_fibre.py \
  --outdir calibration_data/lamp_YYYYMMDD_HHMMSS \
  --prefix lamp_measurement \
  --n-spectra 10 --integration-us 10000 \
  --lamp-file data/LampFiles/030410313_FIB.LMP \
  --correction-out calibration_data/lamp_YYYYMMDD_HHMMSS/correction_factors.csv
```

The correction file has columns `wavelength,correction_factor`.

### 4. *(Optional)* Spectral luminance estimate

If one screen has a known photometer reading and was measured through the same
path as another, use it as a reference to estimate luminance for the others from
their saved spectra:

```bash
uv run python estimate_luminance.py \
  --reference calibration_data/run_A/calibration_YYYYMMDD_HHMMSS.npz \
  --reference-luminance-cd-m2 84 \
  --out calibration_data/luminance_estimate_YYYYMMDD_HHMMSS.csv \
  calibration_data/run_B calibration_data/run_C
```

Add `--colours R,G,B,W` to estimate individual gun maxima as well as full white.

### 5. Build the PsychoPy monitor profile

```bash
python combine_calibrations.py \
  --spectra-file calibration_data/run_YYYYMMDD_HHMMSS/spectra_final_YYYYMMDD_HHMMSS.csv \
  --correction-file calibration_data/lamp_YYYYMMDD_HHMMSS/correction_factors.csv \
  --gamma-params calibration_data/run_YYYYMMDD_HHMMSS/gamma_params_YYYYMMDD_HHMMSS.csv \
  --monitor-name MyMonitor \
  --width-cm 50 --distance-cm 60 --size-pix 1920 1080
```

Writes a `_corrected.csv`, a diagnostic PNG, and — when `--monitor-name` is set —
a PsychoPy monitor `.json` that PsychoPy can load by name.

For very dim (e.g. ND-filtered) runs, subtract the saved dark baseline first with
`--subtract-dark` (it finds the sibling `calibration_*.npz`; point at it with
`--calibration-file` if it lives elsewhere). Negative post-subtraction noise is
clipped to zero unless you pass `--keep-negative`.

Prefer clicking through file pickers? `python combine_calibrations.py --gui`.

---

## Key concepts

- **Gamma / transfer function.** The nonlinear mapping from requested pixel value
  to emitted light. Linearising it is what lets you request "half the contrast"
  and actually get it. `calibrate_screen.py` measures it; `combine_calibrations.py`
  bakes the inverse into the monitor profile.
- **Spectra, not just luminance.** For cone-isolating / silent-substitution work
  you need each gun's full spectral power distribution, because two lights can
  match in luminance yet drive the cones very differently.
- **Fibre / light-pipe correction.** A long fibre transmits some wavelengths
  better than others. Correcting for it (steps 3 + 5) matters most for MEG/MRI/EEG
  rigs where the display is viewed down several metres of light-pipe.
- **Absolute anchoring.** The spectrometer gives relative spectra; a single
  photometer reading (steps 2/4) scales them to real cd/m².

---

## Repository layout

```
calibrate_screen.py        measure_luminance.py     estimate_luminance.py
measure_fibre.py           combine_calibrations.py
archived_scripts/          # older/exploratory scripts, kept for reference
matlab/                    # makeInverseGamma.m
human_data/                # Stockman & Sharpe cone fundamentals (public, from CVRL)
data/LampFiles/            # vendor HL-2000-CAL lamp reference spectra (.LMP)
```

`calibration_data/` is created by the tools to hold your own measurement outputs;
generated run/lamp/luminance directories are git-ignored. **No acquired
measurement data ships in this repository** — only code, documentation, public
reference cone fundamentals, and vendor lamp reference files.

---

## Troubleshooting

- **USB permission errors on Linux** (`pyseabreeze` sees the device but can't
  read it): add a udev rule granting your user access to the Ocean Optics
  vendor/product IDs, e.g. a file in `/etc/udev/rules.d/` with
  `SUBSYSTEM=="usb", ATTRS{idVendor}=="2457", MODE="0666"`, then
  `sudo udevadm control --reload-rules && sudo udevadm trigger` and replug.
- **`cseabreeze` hangs on read:** switch to `--backend pyseabreeze`.
- **PsychoPy / wxPython build errors on Linux:** install your distribution's GUI
  build libraries for wxPython before `uv sync --extra psychopy`.
- **Gamma LUT can't be set on your platform:** run the measurement scripts with
  `--native_gamma` to measure with the native OS/GPU gamma table instead.
- **Display measures as non-additive** (W noticeably different from R+G+B):
  OS colour management is applying a GPU colour matrix. See
  [Before you measure](#before-you-measure-disable-os-colour-management).
  Real LCD/LED panels are additive to within ~1%, so a large discrepancy almost
  always means something in the video path is transforming your colours.

---

## Diagnostics

```bash
uv run python archived_scripts/plot_calibration_diagnostics.py calibration_data/run_YYYYMMDD_HHMMSS
python archived_scripts/psychopy_monitorDiagnostic.py MyMonitor
python archived_scripts/validateMonitor.py MyMonitor
```

---

## Contributing / conventions

See [AGENTS.md](AGENTS.md) for the (human- and agent-facing) editing conventions:
minimal behaviour-preserving changes, no silent changes to calibration maths, and
timestamped output names. [HANDOFF.md](HANDOFF.md) is a session hand-off template.

## License

Released under the [MIT License](LICENSE). © 2026 Alex Wade, Wade Lab,
University of York.
