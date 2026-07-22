from psychopy import visual, core, logging
from psychopy.monitors import Monitor

# ---- Load your calibrated monitor ----
mon_name = "AutoMonitor_20250801"
mon = Monitor(mon_name)            # reads the JSON from the monitors folder
logging.console.setLevel(logging.INFO)
logging.info(f"Loaded monitor '{mon_name}' calibration: {list(mon.currentCalib.keys())}")

# check we really have an LMS matrix available
try:
    print('Checking for an LMS2RGB matrix in the calibration....')

    M = mon.getLMS_RGB()           # 3x3 LMS→RGB
    logging.info(f"LMS→RGB matrix:\n{M}")
except Exception as e:
    logging.warning(f"No LMS calibration available: {e}")

print('About to create a window')
# ---- Create a window using that monitor ----
win = visual.Window(
    size=[1920, 1080], fullscr=True, monitor=mon,
    color=[0, 0, 0], colorSpace='lms', units='deg'
)
print('Window generated using LMS space....')
print("calibrated flag:", mon.currentCalib.get("calibrated"))
print("LMS->RGB:\n", mon.getLMS_RGB())
# ---- Build an S-cone–isolating grating ----
# Positive S-axis (LMS = [0, 0, +contrast]); keep contrast modest to avoid gamut clipping
s_cone_amp = 1  # try 0.05–0.15 first; raise cautiously
grating = visual.GratingStim(
    win=win,
    tex="sin", mask="circle",
    sf=1.0, size=6, ori=0,
    color=[0, 0, s_cone_amp],      # S-cone axis in LMS
    colorSpace='lms',              # let PsychoPy convert LMS→RGB using calibration
    contrast=.4
)
logging.info("Built grating - now adjusting color")
coneM = mon.getLMS_RGB()
print(grating.color)
# ---- Draw for a few seconds ----
clock = core.Clock()
while clock.getTime() < 2:
    grating.draw()
    win.flip()

win.close()
core.quit()
