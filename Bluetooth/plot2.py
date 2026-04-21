import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("imu_tilt_dual_wide.csv")
t = df["t_s"]

pairs = [
    ("X", "imu3_tilt_x_deg", "imu4_tilt_x_deg"),
    ("Y", "imu3_tilt_y_deg", "imu4_tilt_y_deg"),
    ("Z", "imu3_tilt_z_deg", "imu4_tilt_z_deg"),
]

for axis_name, c3, c4 in pairs:
    plt.figure(figsize=(12, 5))
    plt.plot(t, df[c3], label=f"IMU3 {axis_name}")
    plt.plot(t, df[c4], label=f"IMU4 {axis_name}")
    plt.xlabel("Time (s)")
    plt.ylabel("Angle (deg)")
    plt.title(f"{axis_name}-Axis Comparison")
    plt.legend()
    plt.grid(True)
    plt.show()