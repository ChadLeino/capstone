import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("imu_tilt_4_wide.csv")
t = df["t_s"]

for axis in ["x", "y", "z"]:

    fig, axs = plt.subplots(3, 1, figsize=(14, 12), sharex=True)

    # All 4
    axs[0].plot(t, df[f"imu1_tilt_{axis}_deg"], label="IMU1")
    axs[0].plot(t, df[f"imu2_tilt_{axis}_deg"], label="IMU2")
    axs[0].plot(t, df[f"imu3_tilt_{axis}_deg"], label="IMU3")
    axs[0].plot(t, df[f"imu4_tilt_{axis}_deg"], label="IMU4")
    axs[0].set_title(f"All 4 IMUs ({axis.upper()} axis)")
    axs[0].legend()
    axs[0].grid(True)

    # 1 + 3
    axs[1].plot(t, df[f"imu1_tilt_{axis}_deg"], label="IMU1")
    axs[1].plot(t, df[f"imu3_tilt_{axis}_deg"], label="IMU3")
    axs[1].set_title(f"IMU1 + IMU3 ({axis.upper()} axis)")
    axs[1].legend()
    axs[1].grid(True)

    # 2 + 4
    axs[2].plot(t, df[f"imu2_tilt_{axis}_deg"], label="IMU2")
    axs[2].plot(t, df[f"imu4_tilt_{axis}_deg"], label="IMU4")
    axs[2].set_title(f"IMU2 + IMU4 ({axis.upper()} axis)")
    axs[2].legend()
    axs[2].grid(True)

    axs[2].set_xlabel("Time (s)")

    plt.tight_layout()
    plt.show()