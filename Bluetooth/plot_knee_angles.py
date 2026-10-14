#!/usr/bin/env python3
"""Plot the two knee angles in a CSV made by collect_knees.py.

Example:
    ./bluevenv/bin/python plot_knee_angles.py walk_01.csv
"""

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt


def rotation_matrix(roll_deg, pitch_deg, yaw_deg):
    """WIT roll/pitch/yaw sensor-to-world rotation matrix."""
    roll, pitch, yaw = map(math.radians, (roll_deg, pitch_deg, yaw_deg))
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def transpose(matrix):
    return tuple(zip(*matrix))


def matrix_multiply(left, right):
    return tuple(tuple(sum(left[row][index] * right[index][column]
                           for index in range(3)) for column in range(3))
                 for row in range(3))


def rotation_angle_degrees(rotation):
    cosine = (rotation[0][0] + rotation[1][1] + rotation[2][2] - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def wrap_degrees(angle):
    return (angle + 180.0) % 360.0 - 180.0


def raw_orientation(row, imu):
    return rotation_matrix(*(float(row[f"imu{imu}_tilt_{axis}_deg"])
                             for axis in "xyz"))


def numeric_column(rows, name):
    values = []
    for row in rows:
        try:
            values.append(float(row[name]))
        except (KeyError, TypeError, ValueError):
            values.append(float("nan"))
    return values


def saved_angles(rows):
    anatomical = ("knee_1_angle_deg", "knee_2_angle_deg")
    if all(column in rows[0] for column in anatomical):
        return tuple(numeric_column(rows, column) for column in anatomical)
    return None


def reconstructed_3d_angles(rows, reference_row):
    """Calibrate a straight-leg row to 180° and calculate full 3D angles."""
    if not 0 <= reference_row < len(rows):
        raise ValueError("--reference-row must identify a row in the CSV.")
    pairs = ((1, 2), (3, 4))  # thigh, calf
    reference = [matrix_multiply(transpose(raw_orientation(rows[reference_row], thigh)),
                                 raw_orientation(rows[reference_row], calf))
                 for thigh, calf in pairs]
    result = ([], [])
    for row in rows:
        for output, (thigh, calf), neutral in zip(result, pairs, reference):
            relative = matrix_multiply(transpose(raw_orientation(row, thigh)),
                                       raw_orientation(row, calf))
            movement = matrix_multiply(transpose(neutral), relative)
            output.append(180.0 - rotation_angle_degrees(movement))
    return result


def relative_axis_differences(rows, reference_row, axis):
    """Signed calf-minus-thigh Euler change from the calibration row."""
    result = ([], [])
    for output, thigh, calf in zip(result, (1, 3), (2, 4)):
        neutral = (float(rows[reference_row][f"imu{calf}_tilt_{axis}_deg"])
                   - float(rows[reference_row][f"imu{thigh}_tilt_{axis}_deg"]))
        for row in rows:
            difference = (float(row[f"imu{calf}_tilt_{axis}_deg"])
                          - float(row[f"imu{thigh}_tilt_{axis}_deg"]))
            output.append(wrap_degrees(difference - neutral))
    return result


def z_axis_diagnostic(rows, reference_row):
    """Calibrated Z-only angle estimate; useful for checking this mounting."""
    return tuple([180.0 - abs(value) for value in knee_values]
                 for knee_values in relative_axis_differences(rows, reference_row, "z"))


def plot_all_axes(rows, time_s, reference_row, output, show):
    """Plot calibrated signed X/Y/Z differences for checking sensor axes."""
    figure, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for graph, coordinate in zip(axes, "xyz"):
        knee_1, knee_2 = relative_axis_differences(rows, reference_row, coordinate)
        graph.plot(time_s, knee_1, label="Knee 1: IMU2 − IMU1", linewidth=1.6)
        graph.plot(time_s, knee_2, label="Knee 2: IMU4 − IMU3", linewidth=1.6)
        graph.axhline(0, color="black", linewidth=0.8, alpha=0.5)
        graph.set(title=f"Relative {coordinate.upper()} Euler angle", ylabel="Change (degrees)")
        graph.grid(True, alpha=0.3)
        graph.legend(loc="best")
    axes[-1].set_xlabel("Time (s)")
    figure.suptitle("Calibrated relative IMU axes (zero = reference pose)")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    print(f"Saved all-axis diagnostic plot to {output}")
    if show:
        plt.show()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, help="capture CSV to plot")
    parser.add_argument("--output", type=Path,
                        help="PNG output path (default: next to the CSV)")
    parser.add_argument("--reference-row", type=int, default=0,
                        help="known straight-leg row for a raw/older CSV (default: 0)")
    parser.add_argument("--recalculate", action="store_true",
                        help="recalculate 3D angles from raw IMU columns")
    parser.add_argument("--show-z-diagnostic", action="store_true",
                        help="overlay the calibrated Z-only estimate as dashed lines")
    parser.add_argument("--all-axes", action="store_true",
                        help="plot calibrated relative X, Y, and Z differences instead")
    parser.add_argument("--no-show", action="store_true",
                        help="save the PNG without opening a plot window")
    return parser.parse_args()


def main():
    args = parse_args()
    with args.csv_file.open(newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        if not rows:
            raise ValueError(f"{args.csv_file} contains no data rows.")

    time_s = numeric_column(rows, "t_s")
    if args.all_axes:
        output = args.output or args.csv_file.with_name(args.csv_file.stem + "_relative_axes.png")
        plot_all_axes(rows, time_s, args.reference_row, output, not args.no_show)
        return

    angles = None if args.recalculate else saved_angles(rows)
    source_label = "saved 3D angles" if angles is not None else "reconstructed 3D angles"
    if angles is None:
        angles = reconstructed_3d_angles(rows, args.reference_row)
    knee_1, knee_2 = angles

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(time_s, knee_1, label="Knee 1: thigh IMU1 / calf IMU2", linewidth=1.5)
    axis.plot(time_s, knee_2, label="Knee 2: thigh IMU3 / calf IMU4", linewidth=1.5)
    if args.show_z_diagnostic:
        knee_1_z, knee_2_z = z_axis_diagnostic(rows, args.reference_row)
        axis.plot(time_s, knee_1_z, "--", alpha=0.65, label="Knee 1: Z-only diagnostic")
        axis.plot(time_s, knee_2_z, "--", alpha=0.65, label="Knee 2: Z-only diagnostic")
    axis.axhline(180, color="black", linewidth=0.8, alpha=0.5,
                 label="Straight leg (180°)")
    axis.axhline(90, color="black", linewidth=0.8, alpha=0.35, linestyle=":",
                 label="Right angle (90°)")
    axis.set(title=f"Knee angle over time ({source_label})", xlabel="Time (s)",
             ylabel="Knee angle (degrees)", ylim=(0, 185))
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()

    output = args.output or args.csv_file.with_name(args.csv_file.stem + "_knee_angles.png")
    figure.savefig(output, dpi=150)
    print(f"Saved plot to {output}")
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
