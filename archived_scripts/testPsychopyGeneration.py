from psychopy import visual, core, event, monitors
import numpy as np

MONITOR_NAME = "AutoMonitor_20250801"  # <-- exact name in Monitor Center

# --- Load monitor and fetch LMS->RGB matrix ---
mon = monitors.Monitor(MONITOR_NAME)  # loads from monitors folder
M = mon.getLMS_RGB()  # 3x3 LMS->RGB
print("Loaded monitor:", MONITOR_NAME)
print("LMS->RGB matrix:\n", M)

# --- Helper: convert LMS vector to RGB using the monitor matrix ---
def lms_to_rgb(lms_vec, M):
    lms_vec = np.asarray(lms_vec, dtype=float).reshape(3)
    rgb = M.dot(lms_vec)  # RGB = M @ [L,M,S]
    return rgb

# Target: S-cone isolating direction (no L or M), with safe amplitude
amp = 0.2  # start amplitude; will reduce if needed
lms_target = np.array([0.0, 0.0, amp])

rgb = lms_to_rgb(lms_target, M)

# Reduce amplitude until within [-1, 1] gamut for all channels
while np.any(np.abs(rgb) > 1.0) and amp > 1e-4:
    amp *= 0.8
    lms_target[2] = amp
    rgb = lms_to_rgb(lms_target, M)

print(f"Final S-cone amplitude used: {amp:.5f}")
print("RGB for +S direction:", rgb)

# --- Window ---
win = visual.Window(
    size=(1024, 768),
    monitor=mon,          # still set the monitor (size/dist etc. used)
    color=[0, 0, 0],
    colorSpace='rgb',
    units='deg',          # use degrees if your monitor has size/dist set
    fullscr=False
)

# --- S-cone grating ---
# Grating color is a *vector amplitude* that the sinusoidal tex will modulate
grating = visual.GratingStim(
    win=win,
    tex='sin',
    mask='gauss',     # soft-edged patch; set None if you want hard edges
    size=6,           # degrees
    sf=1.0,           # cycles/deg
    color=rgb,        # already in RGB, using your monitor matrix
    colorSpace='rgb',
    phase=0.0
)

# Animate for a few seconds
clock = core.Clock()
while clock.getTime() < 5.0:
    grating.phase += 0.03  # drift
    grating.draw()
    win.flip()
    if event.getKeys(['escape', 'q']):
        break

win.close()
core.quit()
