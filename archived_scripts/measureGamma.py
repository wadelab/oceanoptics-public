import numpy as np
import seabreeze.spectrometers as sb
import matplotlib.pyplot as plt
from psychopy import visual, core
import csv
from datetime import datetime

from scipy.optimize import curve_fit

# Initialize the spectrometer
devices = sb.list_devices()
print(devices)
spec = sb.Spectrometer(devices[0])
spec.integration_time_micros(100000) # 1s integration time in microseconds

# Initialize PsychoPy window
win = visual.Window(size=(1000, 800), color=(-1, -1, -1), units='pix')
win.flip()

# Function to measure spectral response
def measure_spectral_response():
    wavelengths = spec.wavelengths()
    intensities = spec.intensities()
    return wavelengths, intensities

# Function to measure gamma curve
def measure_gamma_curve(brightness_levels):
    gamma_curve = {'R': [], 'G': [], 'B': [],'W': []}
    spectra = {'R': [], 'G': [], 'B': [], 'W': []} # lISTS OF RAW INTENSITIES

    for level in brightness_levels:
        for color in ['R', 'G', 'B','W']:
            if color == 'R':
                win.color = [level, -1, -1]
            elif color == 'G':
                win.color = [-1, level, -1]
            elif color == 'B':
                win.color = [-1, -1, level]
            elif color == 'W':
                win.color = [level, level, level] # In the olden days, we liked to measure R+G+B as well as RGB independently.
                # The response of the three guns together should be identical to the sum of them all independently.
                # One reason it used to be worth doing this was because CRT power supplies sometimes failed to deliver as much power in the W mode as in the independent gun mode.
                

            win.flip()
            win.flip()
            core.wait(1)  # Wait for 1 second to stabilize
                            
            wavelengths, intensities = measure_spectral_response()
            gamma_curve[color].append(np.mean(intensities))
            spectra[color].append(intensities)
    return gamma_curve, spectra, wavelengths

# Cal the function
brightness_levels = np.linspace(-1, 1, 16)  # 8 brightness levels from 0 to 1
gamma_curve, spectra, wavelengths = measure_gamma_curve(brightness_levels)

# Save those three things each to a pkl file


# Save wavelengths to CSV
# Generate a filename based on the date and time:

def generate_filename(base_name):
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{current_time}.csv"

wavelengths_filename = generate_filename('wavelengths')
gamma_curve_filename = generate_filename('gamma_curve')
spectra_filename = generate_filename('spectra')
modelspectra_filename = generate_filename('modelspectra')
with open(wavelengths_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Wavelengths'])  # Header
    writer.writerow(wavelengths)

# Save gamma_curve to CSV (assuming it's a dictionary)
with open(gamma_curve_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Brightness Level', 'R', 'G', 'B'])  # Header
    for i, level in enumerate(brightness_levels):
        writer.writerow([level, gamma_curve['R'][i], gamma_curve['G'][i], gamma_curve['B'][i]])

# Save spectra to CSV (assuming it's a dictionary of lists)
with open(spectra_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Brightness Level', 'Color', 'Intensity'])  # Header
    for color in ['R', 'G', 'B']:
        for i, level in enumerate(brightness_levels):
            for intensity in spectra[color][i]:
                writer.writerow([level, color, intensity])

# Also write out a single file containing the spectra at highest intensity as an nx3

# Get the spectra at the highest brightness level (assuming it's the last level)
highest_brightness_index = len(brightness_levels) - 1
spectra_at_highest = {
    'R': spectra['R'][highest_brightness_index],
    'G': spectra['G'][highest_brightness_index],
    'B': spectra['B'][highest_brightness_index]
}

# Calculate the average spectrum at 0 intensity (background)
spectra_at_0 = {
    'R': spectra['R'][0],
    'G': spectra['G'][0],
    'B': spectra['B'][0]
}
avg_spectrum_at_0 = np.mean([spectra_at_0['R'], spectra_at_0['G'], spectra_at_0['B']], axis=0)

# Subtract background and save to CSV
with open(modelspectra_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['R', 'G', 'B'])  # Header
    for i in range(len(spectra_at_highest['R'])):
        row = [
            spectra_at_highest['R'][i] - avg_spectrum_at_0[i],
            spectra_at_highest['G'][i] - avg_spectrum_at_0[i],
            spectra_at_highest['B'][i] - avg_spectrum_at_0[i]
        ]
        writer.writerow(row)

# Plot gamma curve for each color
plt.figure()
# Use a style with a black/dark background and light text
plt.style.use('dark_background')
for color in ['R', 'G', 'B','W']:
    plt.plot(brightness_levels, gamma_curve[color], color.lower(), label=f'{color} gun', )
plt.xlabel('Brightness Level')
plt.ylabel('Average Intensity')
plt.title('Gamma Curve')
plt.legend()
plt.show()

plt.figure()
# Use a style with a black/dark background and light text
plt.style.use('dark_background')
# Measure and plot spectral response at maximum brightness for each color
for color in ['R', 'G', 'B','W']:
    if color == 'R':
        win.color = [1, -1, -1]
    elif color == 'G':
        win.color = [-1, 1, -1]
    elif color == 'B':
        win.color = [-1, -1, 1]
    elif color == 'W':
        win.color = [.8, .8, .8]
    win.flip()
    win.flip()
    core.wait(1)  # Wait for 1 second to stabilize
    wavelengths, intensities = measure_spectral_response()
    plt.plot(wavelengths, intensities, color.lower(), label=f'{color} gun')

plt.xlabel('Wavelength (nm)')
plt.ylabel('Intensity')
plt.title('Spectral Response at Maximum Brightness')
plt.legend()
plt.show()

# Close PsychoPy window
win.close()

# Save Spectra CSV
# Wavelengths must be ascending (≤ 1 nm jitter tolerated)
spectra_filename_psychopy = generate_filename('psycho_spectra')
with open(spectra_filename_psychopy, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['wavelength_nm', 'R', 'G', 'B'])  # Header
    for i, wavelength in enumerate(wavelengths):
        row = [
            wavelength,
            spectra_at_highest['R'][i] - avg_spectrum_at_0[i],
            spectra_at_highest['G'][i] - avg_spectrum_at_0[i],
            spectra_at_highest['B'][i] - avg_spectrum_at_0[i]
        ]
        writer.writerow(row)



def gamma_function(x, gamma, k, b):
    return k * (x ** gamma) + b

# Calculate gamma, k, and b using curve_fit
def calculate_gamma_params(brightness_levels, measured_intensities):
    # Initial parameter guess
    initial_guess = [2.2, 1.0, 0]  # Typical gamma value starts around 2.2

    # Fit the gamma function to the data
    popt, _ = curve_fit(gamma_function, brightness_levels, measured_intensities, p0=initial_guess)
    return popt  # Returns gamma, k, b

# Save Gamma grid CSV with actual gamma, k, and b values
gamma_grid_filename = generate_filename('gamma_grid')
with open(gamma_grid_filename, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['min_L', 'max_L', 'gamma', 'k', 'b', 'spare'])  # Header

    for color in ['W', 'R', 'G', 'B']:
        min_L = np.min(gamma_curve[color])
        max_L = np.max(gamma_curve[color])
        measured_intensities = gamma_curve[color]
        # Calculate gamma, k, and b
        gamma, k, b = calculate_gamma_params(brightness_levels, measured_intensities)
        writer.writerow([min_L, max_L, gamma, k, b, np.nan])

# Save Gamma grid CSV
# row 0 = combined guns (white), row 1 = red gun, row 2 = green gun, row 3 = blue gun
# columns: min_L, max_L, gamma, k, b, spare
