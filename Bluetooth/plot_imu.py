import os
import pandas as pd
import matplotlib.pyplot as plt

filename = "Bluetooth/imu_angles.csv"

# ---- safety checks ----
if not os.path.exists(filename):
    print(f"{filename} does not exist.")
    raise SystemExit

if os.path.getsize(filename) == 0:
    print(f"{filename} is empty.")
    raise SystemExit

df = pd.read_csv(filename)

if df.empty:
    print(f"{filename} has no data rows.")
    raise SystemExit

# ---- CLEAN DATA ----
df = df.sort_values("t_s")

imus = df["imu"].unique()

# ---- 1. INDIVIDUAL PLOTS ----
for imu in imus:
    sub = df[df["imu"] == imu]

    plt.figure()
    plt.plot(sub["t_s"], sub["yaw_deg"], label="yaw")
    plt.plot(sub["t_s"], sub["roll_deg"], label="roll")
    plt.plot(sub["t_s"], sub["pitch_deg"], label="pitch")

    plt.title(f"{imu}")
    plt.xlabel("Time (s)")
    plt.ylabel("Angle (deg)")
    plt.legend()
    plt.grid()

# ---- 2. COMBINED YAW COMPARISON ----
if len(imus) >= 2:
    imu1 = df[df["imu"] == imus[0]].sort_values("t_s")
    imu2 = df[df["imu"] == imus[1]].sort_values("t_s")

    plt.figure()
    plt.plot(imu1["t_s"], imu1["yaw_deg"], label=f"{imus[0]} yaw")
    plt.plot(imu2["t_s"], imu2["yaw_deg"], label=f"{imus[1]} yaw")

    plt.title("Yaw Comparison")
    plt.xlabel("Time (s)")
    plt.ylabel("Angle (deg)")
    plt.legend()
    plt.grid()

# ---- 3. RELATIVE ANGLE (IMPORTANT) ----
if len(imus) >= 2:
    imu1 = df[df["imu"] == imus[0]].reset_index(drop=True)
    imu2 = df[df["imu"] == imus[1]].reset_index(drop=True)

    # match lengths (quick fix)
    n = min(len(imu1), len(imu2))
    imu1 = imu1.iloc[:n]
    imu2 = imu2.iloc[:n]

    relative_yaw = imu1["yaw_deg"] - imu2["yaw_deg"]

    plt.figure()
    plt.plot(imu1["t_s"], relative_yaw, label="Relative Yaw")

    plt.title("Relative Yaw (Joint Angle)")
    plt.xlabel("Time (s)")
    plt.ylabel("Angle (deg)")
    plt.legend()
    plt.grid()

plt.show()