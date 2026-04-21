import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("imu_tilt_4_wide.csv")
t = df["t_s"]

# --- compute knee angles (Y axis only) ---
knee_1 = df["imu2_tilt_y_deg"] - df["imu1_tilt_y_deg"]
knee_2 = df["imu4_tilt_y_deg"] - df["imu3_tilt_y_deg"]

# --- smoothing (rolling average) ---
# window = 3   # try 3–5
knee_1_smooth = knee_1.rolling(window=2, center=True).median()
knee_2_smooth = knee_2.rolling(window=2, center=True).median()

# --- plot ---
plt.figure(figsize=(14, 6))

plt.plot(t, knee_1, alpha=0.3, label="Knee 1 (raw)")
plt.plot(t, knee_2, alpha=0.3, label="Knee 2 (raw)")

plt.plot(t, knee_1_smooth, linewidth=2, label="Knee 1 (smoothed)")
plt.plot(t, knee_2_smooth, linewidth=2, label="Knee 2 (smoothed)")

plt.xlabel("Time (s)")
plt.ylabel("Knee Angle (deg)")
plt.title("Knee Angle (Y axis) with Smoothing")
plt.grid(True)
plt.legend()
plt.show()