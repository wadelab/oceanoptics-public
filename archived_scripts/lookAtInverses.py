import numpy as np
import matplotlib.pyplot as plt
from numpy.linalg import pinv
from scipy.interpolate import interp1d
import pandas as pd

# 1. Define wavelength axis
nm = np.arange(380, 781, 1)  # 1 nm steps

# 2. Define synthetic monitor SPDs (RGB)
# Each SPD is a Gaussian-like distribution centered in the expected range
def gaussian(wl, center, width):
    return np.exp(-0.5 * ((wl - center) / width) ** 2)

spd_r = gaussian(nm, 620, 20)
spd_g = gaussian(nm, 540, 25)
spd_b = gaussian(nm, 450, 18)
rgb_spd = np.vstack([spd_r, spd_g, spd_b])  # shape: (3 x N)

# 3. Define synthetic LMS fundamentals (Stockman & Sharpe style)
# Source: rough approximations, could be replaced with real data
l_cone = gaussian(nm, 560, 25)
m_cone = gaussian(nm, 530, 25)
s_cone = gaussian(nm, 440, 20)
lms = np.vstack([l_cone, m_cone, s_cone])  # shape: (3 x N)

# 4. Compute LMS2RGB matrix using PsychoPy logic
lms2rgb = rgb_spd @ pinv(lms)

# 5. Display the matrix
lms2rgb_df = pd.DataFrame(lms2rgb, columns=["L", "M", "S"], index=["R", "G", "B"])

# 6. Also visualize SPDs and LMS curves
plt.plot(nm, spd_r, label='Red SPD')
plt.plot(nm, spd_g, label='Green SPD')
plt.plot(nm, spd_b, label='Blue SPD')
plt.plot(nm, l_cone, '--', label='L-cone')
plt.plot(nm, m_cone, '--', label='M-cone')
plt.plot(nm, s_cone, '--', label='S-cone')
plt.xlabel('Wavelength (nm)')
plt.ylabel('Relative Power / Sensitivity')
plt.title('Synthetic RGB SPDs and LMS Fundamentals')
plt.legend()
plt.grid(True)
plt.tight_layout()

import ace_tools as tools; tools.display_dataframe_to_user(name="LMS2RGB Matrix", dataframe=lms2rgb_df)
