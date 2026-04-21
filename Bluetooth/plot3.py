import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("imu_tilt_4_wide.csv")
t = df["t_s"]

imus = ["imu1", "imu2", "imu3", "imu4"]
axes = ["x", "y", "z"]

for axis in axes:
    plt.figure(figsize=(12, 5))

    for imu in imus:
        col = f"{imu}_tilt_{axis}_deg"
        plt.plot(t, df[col], label=f"{imu.upper()} {axis.upper()}")

    plt.xlabel("Time (s)")
    plt.ylabel("Angle (deg)")
    plt.title(f"{axis.upper()}-Axis Comparison (All IMUs)")
    plt.legend()
    plt.grid(True)
    plt.show()