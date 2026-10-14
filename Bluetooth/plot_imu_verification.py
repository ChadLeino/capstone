#!/usr/bin/env python3
"""Plot the IMU1/IMU2 X axes and derived knee angle from verify_imus.py data.

Example:
    ./bluevenv/bin/python plot_imu_verification.py imu_check.csv
"""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="CSV made by verify_imus.py")
    parser.add_argument("--output", type=Path,
                        help="PNG path (default: next to the CSV)")
    parser.add_argument("--include-unsynced", action="store_true",
                        help="also plot rows whose orientation packets exceed the sync threshold")
    parser.add_argument("--no-show", action="store_true",
                        help="save PNG without opening a window")
    return parser.parse_args()


def main():
    args = parse_args()
    with args.csv_file.open(newline="") as source:
        rows = list(csv.DictReader(source))

    selected = []
    for row in rows:
        try:
            # Avoid graphing initial rows before both IMUs have an X angle.
            float(row["imu1_angle_x_deg"])
            float(row["imu2_angle_x_deg"])
            if not args.include_unsynced and row["pair_in_sync"].lower() != "true":
                continue
            selected.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    if not selected:
        raise ValueError("No usable synchronized IMU1/IMU2 X-angle rows were found.")

    time_s = [float(row["host_t_s"]) for row in selected]
    imu1_x = [float(row["imu1_angle_x_deg"]) for row in selected]
    imu2_x = [float(row["imu2_angle_x_deg"]) for row in selected]
    # IMU1 is above the knee and IMU2 is below it. This is the requested
    # direct X-axis calculation, with no neutral-pose or 3D correction.
    knee_angle = [180.0 - (imu2 - imu1) for imu1, imu2 in zip(imu1_x, imu2_x)]

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(time_s, imu1_x, label="IMU1 X (above knee)", color="tab:blue")
    axes[0].plot(time_s, imu2_x, label="IMU2 X (below knee)", color="tab:orange")
    axes[0].set(title="IMU X-axis orientations", ylabel="X angle (degrees)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(ncol=3)

    axes[1].plot(time_s, knee_angle, color="black", linewidth=1.6,
                 label="180 − (IMU2 X − IMU1 X)")
    axes[1].axhline(180, color="tab:gray", linestyle="--", label="180° reference")
    axes[1].set(title="Derived X-axis knee angle", xlabel="Time (s)",
                ylabel="Knee angle (degrees)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    figure.tight_layout()

    output = args.output or args.csv_file.with_name(args.csv_file.stem + "_imu_and_knee.png")
    figure.savefig(output, dpi=150)
    print(f"Saved plot to {output} ({len(selected)} rows used).")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
