"""Tests for the correction-factor maths in measure_fibre.py. No hardware needed.

Run from the repository root:  uv run --with pytest pytest tests
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure_fibre as mf  # noqa: E402

# USB2000 wavelength calibration (EEPROM of the reference unit) and dark level.
WL = sum(c * np.arange(2048.0) ** k
         for k, c in enumerate((340.5639150, 0.380137195, -1.93830e-05, -1.47741e-09)))
DARK = 131.0


def sensitivity(wl):
    """Detector + fibre sensitivity: weak in the blue, like the real fibre path."""
    return np.exp(-(((wl - 600.0) / 150.0) ** 2))


def halogen(wl):
    """Lamp spectrum: a 3100 K blackbody, relative units.

    With sensitivity() and a 2500-count peak this gives about 30, 61, 269, 1729
    and 2048 counts above dark at 380, 400, 450, 560 and 700 nm, close to the real
    HL-2000-CAL measurement through fibre 727-733-2447 (27, 58, 285, 1733, 2158).
    """
    x = np.asarray(wl, dtype=float) * 1e-9
    return 1e-30 * x ** -5 / np.expm1(6.626e-34 * 2.998e8 / (x * 1.381e-23 * 3100.0))


def write_inputs(tmp_path, peak_counts=2500.0, n=5):
    lamp_wl = np.arange(300.0, 1051.0, 1.0)
    lamp_file = tmp_path / "lamp.LMP"
    np.savetxt(lamp_file, np.column_stack([lamp_wl, halogen(lamp_wl)]), fmt="%.6g")

    signal = halogen(WL) * sensitivity(WL)
    signal *= peak_counts / signal.max()
    signal[:25] = 0.0                      # masked pixels see no light
    spectrum = DARK + signal
    spectrum[0] = 0.0                      # pixel 0 of the USB2000 always reads 0
    df = pd.DataFrame({"wavelength_nm": WL})
    for i in range(n):
        df[f"intensity_{i + 1}"] = spectrum
    meas_file = tmp_path / "lamp_measurement.csv"
    df.to_csv(meas_file, index=False)
    return lamp_file, meas_file


def run(tmp_path, start_nm=380, **kw):
    lamp_file, meas_file = write_inputs(tmp_path, **kw)
    out = mf.generate_correction_factors(
        lamp_file=lamp_file, measurement_file=meas_file, output_file=tmp_path / "corr.csv",
        start_nm=start_nm, stop_nm=740, step_nm=5, plot=False, fibre_id="test")
    return pd.read_csv(out)


def test_correction_recovers_true_sensitivity_across_the_spectrum(tmp_path):
    corr = run(tmp_path)
    w = corr["wavelength"].to_numpy()
    f = corr["correction_factor"].to_numpy()
    # correction x sensitivity must be flat, including at the blue end where the
    # old minimum-subtraction left the dark level in and was several times out
    product = f * sensitivity(w)
    assert np.ptp(product) / product.mean() < 0.01


def test_output_keeps_its_columns(tmp_path):
    corr = run(tmp_path)
    assert list(corr.columns) == ["wavelength", "correction_factor", "fibre_id"]
    assert (corr["fibre_id"] == "test").all()


def test_minimum_is_not_used_as_dark_level():
    spectrum = np.array([0.0, 120, 130, 130, 130, 500, 900])
    signal, dark = mf.subtract_dark(spectrum, slice(2, 5))
    assert dark == 130
    assert signal[-1] == 770


def test_wrong_dark_pixels_are_caught(tmp_path):
    lamp_file, meas_file = write_inputs(tmp_path)
    with pytest.raises(ValueError, match="No signal above the dark level"):
        mf.generate_correction_factors(
            lamp_file=lamp_file, measurement_file=meas_file, output_file=tmp_path / "c.csv",
            start_nm=380, stop_nm=740, step_nm=5, plot=False, fibre_id="test",
            dark_pixels=mf.parse_pixel_range("1500-1600"))  # lit pixels, not masked ones


def test_low_blue_signal_warns(tmp_path, capsys):
    run(tmp_path)  # ~30 counts above dark at 380 nm, as in the real measurement
    assert "Warning: under 50 counts above dark at 380-" in capsys.readouterr().out
    run(tmp_path, start_nm=450)  # ~270 counts at 450 nm: no warning
    assert "Warning" not in capsys.readouterr().out


def test_parse_pixel_range():
    assert mf.parse_pixel_range("2-24") == slice(2, 25)
    with pytest.raises(ValueError):
        mf.parse_pixel_range("24-2")
    with pytest.raises(ValueError):
        mf.parse_pixel_range("two")
