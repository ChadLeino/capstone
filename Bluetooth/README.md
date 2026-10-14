# Four-IMU knee collector

`collect_knees.py` is the consolidated collector for the four configured WIT
IMUs. It waits and retries until every expected device connects, waits for
Enter, then writes time-aligned rows until Ctrl+C.

| Placement | Label | Bluetooth address |
| --- | --- | --- |
| Above knee 1 | IMU1 | `D4:3F:17:2F:EC:51` |
| Below knee 1 | IMU2 | `D6:DC:FD:A3:9D:59` |
| Above knee 2 | IMU3 | `D0:01:6C:93:1C:F5` |
| Below knee 2 | IMU4 | `F7:D7:39:21:2A:72` |

Run it from this directory with the installed environment:

```bash
./bluevenv/bin/python collect_knees.py --output walk_01.csv
```

Each completed row contains the four synchronized IMU samples and two 3D
anatomical knee angles: `knee_1_angle_deg` and `knee_2_angle_deg`. Keep both
legs straight and still when you press Enter: the first synchronized pose is
calibrated to 180 degrees. A 90-degree calf-to-thigh bend then reports about
90 degrees. IMU1 and IMU3 are the thigh sensors; IMU2 and IMU4 are the calf
sensors. The CSV also keeps the original one-axis differences for debugging:
`IMU2.y - IMU1.y` and `IMU4.y - IMU3.y`.

## Plot a capture

`plot_knee_angles.py` is offline: it never connects to or changes the IMUs.
It plots saved 3D knee angles from a new capture, or reconstructs them from
the four raw orientations in an older CSV:

```bash
./bluevenv/bin/python plot_knee_angles.py walk_01.csv
```

For the vertical, forward-facing mounting used in `walk_01.csv`, the dominant
relative-motion axis is sensor Z. The plot still uses the full 3D relative
orientation, which is more robust to small mounting offsets. Add
`--show-z-diagnostic` to compare the Z-only estimate. Use
`--reference-row N` when a raw CSV's known straight-leg calibration is not
its first row.

To inspect the signed calibrated change on every Euler axis instead, run:

```bash
python plot_knee_angles.py walk_01.csv --all-axes
```

Use `--zero-at-start` to define the first synchronized posture after Enter as
zero degrees. This is useful when only changes from a neutral standing pose
matter.

For a live ML consumer, mirror the same CSV rows to standard output while
also saving the file:

```bash
./bluevenv/bin/python collect_knees.py --output walk_01.csv --stream-stdout | ./your_model_consumer.py
```

When `--stream-stdout` is enabled, progress messages go to standard error, so
standard output remains valid CSV. The consumer receives one header row then
one time-aligned sample row at a time. `--max-skew` controls the largest time
gap allowed between the four samples in a row (75 ms by default).

## Verify raw IMU data (IMU1 and IMU2)

`verify_imus.py` is the simple diagnostic recorder for the two sensors in
question. It connects to IMU1 and IMU2, waits for Enter, then writes a
fixed-rate CSV until Ctrl+C:

```bash
./bluevenv/bin/python verify_imus.py --output imu_check.csv
```

The default is 20 rows per second. Each row holds the latest received
accelerometer (g), gyro (degrees/s), magnetometer raw counts, Euler angles
(degrees), quaternion, temperature, packet type/raw bytes, and receive time
for both IMUs. Blank values mean the sensor did not broadcast that frame type.
`angle_skew_s` and `pair_in_sync` show whether the two latest orientation
packets arrived within the 75 ms synchronization threshold; questionable rows
are preserved rather than silently dropped.

Use `--rate 40` for a quicker capture (1--100 Hz), and `--max-skew 0.05` to
use a 50 ms synchronization threshold.

Plot a verification recording:

```bash
./bluevenv/bin/python plot_imu_verification.py imu_check.csv
```

The first plot shows the X angles for IMU1 (above the knee) and IMU2 (below
the knee). The lower plot uses `180 - (IMU2_X - IMU1_X)`. Add
`--include-unsynced` only when diagnosing Bluetooth timing.

## Live six-graph IMU view

To view IMU1 and IMU2 live without calculating a knee angle, run:

```bash
./bluevenv/bin/python live_plot_imus.py
```

It opens six scrolling graphs: X, Y, and Z orientation for IMU1, followed by
X, Y, and Z orientation for IMU2. The default view retains the latest 15
seconds; use `--window 30` for a 30-second history.
