import serial
import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt
from collections import deque
import numpy as np
import time

PORT = "/dev/tty.usbmodem1101"
BAUDRATE = 115200

REST_TIME = 30
BREATH_TIME = 60
TOTAL_TIME = REST_TIME + BREATH_TIME

time_data = deque(maxlen=1000)
pulse_data = deque(maxlen=1000)
smooth_data = deque(maxlen=1000)

rest_bpm = []
breath_bpm = []

window_size = 10


def get_bpm(times, values):
    if len(values) < 80:
        return 0

    t = list(times)[-250:]
    v = list(values)[-250:]

    total = 0
    for value in v:
        total += value

    ave = total / len(v)
    max_value = max(v)
    min_value = min(v)

    threshold = ave + (max_value - min_value) * 0.25

    peaks = []

    for i in range(1, len(v) - 1):
        if v[i] > threshold:
            if v[i] > v[i - 1] and v[i] > v[i + 1]:
                if len(peaks) == 0:
                    peaks.append(t[i])
                else:
                    if t[i] - peaks[-1] > 0.4:
                        peaks.append(t[i])

    if len(peaks) < 2:
        return 0

    interval_total = 0
    interval_count = 0

    for i in range(1, len(peaks)):
        interval_total += peaks[i] - peaks[i - 1]
        interval_count += 1

    if interval_count == 0:
        return 0

    interval_ave = interval_total / interval_count

    if interval_ave <= 0:
        return 0

    bpm = 60 / interval_ave

    if bpm < 40 or bpm > 180:
        return 0

    return round(bpm, 1)


def get_average(data):
    total = 0
    count = 0

    for value in data:
        if value > 0:
            total += value
            count += 1

    if count == 0:
        return 0

    return round(total / count, 1)


def get_max(data):
    valid = []

    for value in data:
        if value > 0:
            valid.append(value)

    if len(valid) == 0:
        return 0

    return round(max(valid), 1)


ser = serial.Serial(PORT, BAUDRATE, timeout=1)
time.sleep(2)

plt.ion()

fig, ax = plt.subplots(figsize=(10, 6))

line1, = ax.plot([], [], label="Pulse voltage")
line2, = ax.plot([], [], label="Smoothed pulse")

ax.set_xlabel("Time (s)")
ax.set_ylabel("Pulse voltage (V)")
ax.set_title("Pulse Sensor Data")
ax.grid(True)
ax.legend()

text_info = ax.text(
    0.02,
    0.95,
    "",
    transform=ax.transAxes,
    verticalalignment="top"
)

plt.show()

last_bpm_time = 0
current_bpm = 0

try:
    while True:
        line = ser.readline().decode(errors="ignore").strip()

        if line == "":
            plt.pause(0.01)
            continue

        if line.startswith("DATA"):
            data = line.split(",")

            elapsed = float(data[1])
            pulse = float(data[2])
            status = data[3]

            time_data.append(elapsed)
            pulse_data.append(pulse)

            if len(pulse_data) >= window_size:
                recent = list(pulse_data)[-window_size:]
                smooth_value = np.mean(recent)
            else:
                smooth_value = pulse

            smooth_data.append(smooth_value)

            if elapsed - last_bpm_time >= 1:
                current_bpm = get_bpm(time_data, smooth_data)

                if current_bpm > 0:
                    if elapsed < REST_TIME:
                        rest_bpm.append(current_bpm)
                    elif elapsed < TOTAL_TIME:
                        breath_bpm.append(current_bpm)

                last_bpm_time = elapsed

            rest_ave = get_average(rest_bpm)
            breath_ave = get_average(breath_bpm)
            max_value = get_max(rest_bpm + breath_bpm)

            diff = 0
            if rest_ave > 0 and breath_ave > 0:
                diff = round(rest_ave - breath_ave, 1)

            line1.set_data(time_data, pulse_data)
            line2.set_data(time_data, smooth_data)

            ax.relim()
            ax.autoscale_view()

            text = (
                "Status: {}\n"
                "Time: {:.1f} s\n"
                "Current BPM: {}\n"
                "Rest Avg BPM: {}\n"
                "Breathing Avg BPM: {}\n"
                "Max BPM: {}\n"
                "Difference: {}"
            ).format(
                status,
                elapsed,
                current_bpm,
                rest_ave,
                breath_ave,
                max_value,
                diff
            )

            text_info.set_text(text)
            ax.set_title("Pulse Relaxation Support System")

            plt.pause(0.01)

        elif line == "START":
            print("計測開始")

        elif line == "END":
            rest_ave = get_average(rest_bpm)
            breath_ave = get_average(breath_bpm)
            max_value = get_max(rest_bpm + breath_bpm)

            diff = 0
            if rest_ave > 0 and breath_ave > 0:
                diff = round(rest_ave - breath_ave, 1)

            print("計測終了")
            print("呼吸誘導前の平均心拍:", rest_ave, "BPM")
            print("呼吸誘導後の平均心拍:", breath_ave, "BPM")
            print("最大心拍:", max_value, "BPM")
            print("前後の平均心拍差:", diff, "BPM")

        else:
            print(line)

except KeyboardInterrupt:
    print("終了します")


finally:
    ser.close()