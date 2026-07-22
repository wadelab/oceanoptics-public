import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from psychopy.monitors import Monitor
from scipy.interpolate import interp1d
from pathlib import Path
import datetime as _dt

class CalibrationTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spectra Calibration Tool")

        # Create UI elements for file selection and entry
        # Spectra file input
        self.spectra_label = tk.Label(self, text="Spectra File:")
        self.spectra_label.grid(row=0, column=0, padx=10, pady=5)
        self.spectra_entry = tk.Entry(self, width=50)
        self.spectra_entry.grid(row=0, column=1, padx=10, pady=5)
        self.spectra_button = tk.Button(self, text="Browse", command=self.load_spectra_file)
        self.spectra_button.grid(row=0, column=2, padx=10, pady=5)
        
        # Correction file input
        self.correction_label = tk.Label(self, text="Correction File:")
        self.correction_label.grid(row=1, column=0, padx=10, pady=5)
        self.correction_entry = tk.Entry(self, width=50)
        self.correction_entry.grid(row=1, column=1, padx=10, pady=5)
        self.correction_button = tk.Button(self, text="Browse", command=self.load_correction_file)
        self.correction_button.grid(row=1, column=2, padx=10, pady=5)

        # Monitor profile name input
        self.monitor_name_label = tk.Label(self, text="Monitor Name:")
        self.monitor_name_label.grid(row=2, column=0, padx=10, pady=5)
        self.monitor_name_entry = tk.Entry(self, width=50)
        self.monitor_name_entry.grid(row=2, column=1, padx=10, pady=5)

        # Button to process files and perform spectral correction
        self.process_button = tk.Button(self, text="Process", command=self.process_files)
        self.process_button.grid(row=3, column=1, padx=10, pady=20)

        # Button to generate a PsychoPy monitor profile
        self.generate_monitor_button = tk.Button(self, text="Generate Monitor Profile", command=self.generate_monitor_profile)
        self.generate_monitor_button.grid(row=4, column=1, padx=10, pady=20)

        # Button to exit the application
        self.finished_button = tk.Button(self, text="Finished", bg="red", command=self.quit)
        self.finished_button.grid(row=5, column=1, padx=10, pady=20)

        # Frames to hold plots for visual data inspection
        self.spectra_plot_frame = tk.Frame(self)
        self.spectra_plot_frame.grid(row=6, column=0, columnspan=3, pady=10)

        self.correction_plot_frame = tk.Frame(self)
        self.correction_plot_frame.grid(row=7, column=0, columnspan=3, pady=10)

    def load_spectra_file(self):
        # Pop up a file dialog for the user to select a spectra file
        filename = filedialog.askopenfilename(filetypes=[("Spectra Files", "*.csv")])
        if filename:
            self.spectra_entry.delete(0, tk.END)
            self.spectra_entry.insert(0, filename)
    
    def load_correction_file(self):
        # Pop up a file dialog for the user to select a correction file
        filename = filedialog.askopenfilename(filetypes=[("Correction Files", "*.csv")])
        if filename:
            self.correction_entry.delete(0, tk.END)
            self.correction_entry.insert(0, filename)
    
    def process_files(self):
        # Load and interpolate the spectral data and apply correction factors
        spectra_file = self.spectra_entry.get()
        correction_file = self.correction_entry.get()

        if not spectra_file or not correction_file:
            messagebox.showwarning("Input Error", "Please select both spectra and correction files before proceeding.")
            return

        # Load spectra and correction data
        screen_df = pd.read_csv(spectra_file)
        corr_df = pd.read_csv(correction_file)

        # Interpolate to standard wavelength range (380 to 740 nm)
        interp_wavelengths = np.arange(380, 745, 5)
        screen_interp = pd.DataFrame({'wavelength': interp_wavelengths})

        # Interpolate R, G, B values linearly and apply extrapolation for out-of-range values
        for col in ['R', 'G', 'B']:
            interp_func = interp1d(screen_df['wavelength_nm'], screen_df[col], kind='linear', fill_value="extrapolate")
            screen_interp[col] = interp_func(interp_wavelengths)
            
        # Normalize channel data by removing minimum value and scaling by maximum
        min_val = screen_interp[['R', 'G', 'B']].values.min()
        for col in ['R', 'G', 'B']:
            screen_interp[col] -= min_val
        max_val = screen_interp[['R', 'G', 'B']].values.max()
        for col in ['R', 'G', 'B']:
            screen_interp[col] /= max_val
        
        # Apply correction factors
        corr_interp = interp1d(corr_df['wavelength'], corr_df['correction_factor'], kind='linear', fill_value="extrapolate")(interp_wavelengths)

        # Calculate corrected values and normalize again
        for col in ['R', 'G', 'B']:
            screen_interp[f'{col}_corrected'] = screen_interp[col] * corr_interp
        max_val_corrected = screen_interp[[f'{col}_corrected' for col in ['R', 'G', 'B']]].values.max()
        for col in ['R', 'G', 'B']:
            screen_interp[f'{col}_corrected'] /= max_val_corrected

        # Save corrected data
        output_path = spectra_file.replace('.csv', '_corrected.csv')
        screen_interp.to_csv(output_path, index=False)
        print(f"Corrected spectra saved to {output_path}")
        messagebox.showinfo("Processing Complete", f"Corrected spectra saved to {output_path}.")

        # Render plots within the GUI
        self.display_spectra_plot(screen_interp, interp_wavelengths)
        self.display_correction_plot(interp_wavelengths, corr_interp)

    def display_spectra_plot(self, screen_interp, interp_wavelengths):
        # Plot original vs corrected spectra within the GUI
        fig, ax = plt.subplots(figsize=(8, 4))
        for col in ['R', 'G', 'B']:
            ax.plot(interp_wavelengths, screen_interp[col], label=f'{col} (original)')
            ax.plot(interp_wavelengths, screen_interp[f'{col}_corrected'], label=f'{col} (corrected)')
        ax.set_xlabel('Wavelength (nm)')
        ax.set_ylabel('Value')
        ax.set_title('Original vs Corrected Screen Spectra')
        ax.legend()
        canvas = FigureCanvasTkAgg(fig, master=self.spectra_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def display_correction_plot(self, interp_wavelengths, corr_interp):
        # Plot correction factor as a function of wavelength
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(interp_wavelengths, corr_interp, label='Correction Factor', linestyle='--', color='black')
        ax.set_xlabel('Wavelength (nm)')
        ax.set_ylabel('Correction Factor')
        ax.set_title('Correction Factors over Wavelength')
        ax.legend()
        canvas = FigureCanvasTkAgg(fig, master=self.correction_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def generate_monitor_profile(self):
        # Generates and saves a PsychoPy monitor profile
        monitor_name = self.monitor_name_entry.get()
        if not monitor_name:
            messagebox.showwarning("Input Error", "Please enter a monitor name before generating profile.")
            return

        spectra_file = self.spectra_entry.get().replace('.csv', '_corrected.csv')
        if not Path(spectra_file).exists():
            messagebox.showwarning("Processing Error", "Corrected spectra not available. Process the files first.")
            return

        try:
            # Load corrected spectral data
            nm, rgb = self._load_corrected_spectra(spectra_file)
            # Create a monitor profile using the spectral data
            self._create_MON_profile(monitor_name, nm, rgb)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate monitor profile: {e}")

    def _load_corrected_spectra(self, csv_path):
        # Load corrected spectra data for monitor profiling
        df = pd.read_csv(csv_path)
        nm = df['wavelength'].values
        rgb = df[['R_corrected', 'G_corrected', 'B_corrected']].values
        return nm, rgb

    def _create_MON_profile(self, name, nm, rgb):
        # Calculate and save the monitor profile using human cone data
        width_cm = 50.0  # Default width; can be adjusted
        distance_cm = 60.0  # Default viewing distance; can be adjusted

        # Load human cone fundamentals
        cone_csv = Path('human_data/ss10q_1.csv')
        if not cone_csv.exists():
            messagebox.showwarning("Data Error", "Human spectral data missing.")
            return

        try:
            cone_df = pd.read_csv(cone_csv, header=None)
            cone_nm = cone_df[0].values
            cone_lms = cone_df[[1, 2, 3]].values.T  # Assuming columns for L, M, S
            cone_lms = 10** cone_lms  # Convert from log-scale

            # Interpolate LMS data to match corrected spectral data across wavelengths
            interp_cone = interp1d(cone_nm, cone_lms, axis=1, kind='linear', fill_value="extrapolate")
            cone_lms_resampled = interp_cone(nm)

            rgb = np.nan_to_num(rgb, nan=0.0)
            cone_lms_resampled = np.nan_to_num(cone_lms_resampled, nan=0.0)

            # Compute the LMS to RGB conversion matrix
            RGB2LMS = rgb.T @ cone_lms_resampled.T
            M = np.linalg.pinv(RGB2LMS) * 100

            # Create a new PsychoPy monitor profile
            mon = Monitor(name=name, width=width_cm, distance=distance_cm)
            new_nm = np.arange(380, 721, 1)
            interp_func = interp1d(nm, rgb, axis=0, kind='linear', fill_value="extrapolate")
            rgb_resampled = interp_func(new_nm)
            rgb_resampled /= np.max(rgb_resampled, axis=0)
            mon.setSpectra(new_nm, rgb_resampled.T)
            mon.setLMS_RGB(M.T)
            mon.setGamma([2.2, 2.2, 2.2])  # Default gamma; can be adjusted
            mon.save()

            profile_path = Path.home() / ".psychopy3" / "monitors" / f"{name}.json"
            messagebox.showinfo("Success", f"Monitor profile saved to {profile_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed during monitor profile creation: {e}")

if __name__ == "__main__":
    app = CalibrationTool()
    app.mainloop()