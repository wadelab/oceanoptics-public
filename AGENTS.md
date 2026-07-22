# AGENTS.md

This file defines working rules for future coding-agent (and human) edits in this
repository.

## Project Scope
- Repository purpose: monitor/spectrometer calibration tooling and PsychoPy
  monitor-profile generation.
- Active calibration entry points in the repository root:
  - `calibrate_screen.py`
  - `measure_luminance.py`
  - `estimate_luminance.py`
  - `measure_fibre.py`
  - `combine_calibrations.py`
- Legacy/exploratory scripts live in `archived_scripts/`.
- MATLAB code location: `matlab/`.
- Public reference data:
  - `human_data/` — Stockman & Sharpe cone fundamentals (from CVRL).
  - `data/LampFiles/` — vendor HL-2000-CAL lamp reference spectra.
- Your own measurement outputs are written under `calibration_data/`, which is
  git-ignored. No acquired measurement data is committed to this repository.

## Environment and Dependencies
- Use uv for Python environment and dependency management.
- Typical setup pattern:
  - uv venv
  - source .venv/bin/activate
  - uv sync
- For PsychoPy-specific workflows, use the optional extra when available:
  - uv sync --extra psychopy
- Do not introduce new dependencies unless required for the requested task.
- For the reference Ocean Optics USB2000, `pyseabreeze` reads spectra reliably in
  the uv venv; `cseabreeze` may list the device but has hung during reads.

## Editing Rules
- Make minimal, behavior-preserving changes unless behavior changes are explicitly
  requested.
- Keep scientific and calibration logic stable unless the user asks to modify it.
- Avoid broad rewrites and unrelated formatting changes.
- Prefer small, reviewable diffs.

## Data Safety
- Do not commit acquired measurement data (spectra, gamma curves, `.npz` bundles,
  photometer logs). Keep it under `calibration_data/`, which is git-ignored.
- New generated outputs should use clear, timestamped names.

## Validation
- After edits, run lightweight checks when feasible:
  - Python syntax/error checks on changed files.
  - Existing test or validation scripts if available.
- Report what was validated and what was not.

## Documentation Updates
- If files are moved or the workflow changes, update `README.md`, `HOWTO.md`, and
  this file when relevant.
