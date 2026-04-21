import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("imu_tilt_4_wide.csv")
t = df["t_s"]

fig, axs = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

for i, axis in enumerate(["x", "y", "z"]):
    knee_1 = df[f"imu2_tilt_{axis}_deg"] - df[f"imu1_tilt_{axis}_deg"]
    knee_2 = df[f"imu4_tilt_{axis}_deg"] - df[f"imu3_tilt_{axis}_deg"]

    axs[i].plot(t, knee_1, label="Knee 1 (IMU2 - IMU1)")
    axs[i].plot(t, knee_2, label="Knee 2 (IMU4 - IMU3)")
    axs[i].set_title(f"Knee Angle ({axis.upper()} axis)")
    axs[i].set_ylabel("Relative Angle (deg)")
    axs[i].grid(True)
    axs[i].legend()

axs[2].set_xlabel("Time (s)")
plt.tight_layout()
plt.show()