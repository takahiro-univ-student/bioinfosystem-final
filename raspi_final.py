import rp2
import network
import socket
import time
import json
from machine import ADC, Pin, PWM

SSID = "SSID-7MENRF"
PASSWORD = "bd3fab3e"

pulse_sensor = ADC(27)
board_led = Pin("LED", Pin.OUT)

breath_led = PWM(Pin(15))
breath_led.freq(1000)

VDD = 3.3
CONVERSION_FACTOR = VDD / 65535

REST_TIME = 30
BREATH_TIME = 60
TOTAL_TIME = REST_TIME + BREATH_TIME

SAMPLE_TIME = 20

INHALE_TIME = 4
EXHALE_TIME = 8
BREATH_CYCLE = INHALE_TIME + EXHALE_TIME

alpha = 0.2
smooth_value = 0

data_list = []
rest_bpm = []
breath_bpm = []

last_phase = ""
started = False
finished = False

start_time = 0
last_sample_time = 0
last_bpm_time = 0
breath_start = False
current_bpm = 0


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    max_wait = 15

    while max_wait > 0:
        if wlan.status() == 3:
            break
        print("Waiting for connection...")
        max_wait -= 1
        time.sleep(1)

    if wlan.status() != 3:
        raise RuntimeError("Network connection failed")

    print("Connected")
    print("IP:", wlan.ifconfig()[0])
    print("Open browser: http://" + wlan.ifconfig()[0])

    return wlan


def read_pulse():
    raw = pulse_sensor.read_u16()
    return raw * CONVERSION_FACTOR


def blink_board_led():
    for i in range(3):
        board_led.on()
        time.sleep(0.3)
        board_led.off()
        time.sleep(0.3)


def blink_breath_led():
    for i in range(2):
        breath_led.duty_u16(65535)
        time.sleep(0.08)
        breath_led.duty_u16(0)
        time.sleep(0.08)


def breath_led_control(elapsed):
    global last_phase

    if elapsed < REST_TIME:
        breath_led.duty_u16(0)
        last_phase = "REST"
        return "REST"

    elif elapsed < TOTAL_TIME:
        breath_time = elapsed - REST_TIME
        phase_time = breath_time % BREATH_CYCLE

        if phase_time < INHALE_TIME:
            phase = "INHALE"
            brightness = phase_time / INHALE_TIME
        else:
            phase = "EXHALE"
            brightness = 1 - ((phase_time - INHALE_TIME) / EXHALE_TIME)

        if phase != last_phase:
            blink_breath_led()
            last_phase = phase

        brightness = brightness * brightness
        duty = int(brightness * 65535)
        breath_led.duty_u16(duty)

        return phase

    else:
        breath_led.duty_u16(0)
        return "FINISHED"


def get_bpm(data):
    if len(data) < 80:
        return 0

    use_data = data[-250:]

    times = []
    values = []

    for d in use_data:
        times.append(d[0])
        values.append(d[1])

    total = 0

    for v in values:
        total += v

    ave = total / len(values)
    max_value = max(values)
    min_value = min(values)

    threshold = ave + (max_value - min_value) * 0.25

    peaks = []

    for i in range(1, len(values) - 1):
        if values[i] > threshold:
            if values[i] > values[i - 1] and values[i] > values[i + 1]:
                if len(peaks) == 0:
                    peaks.append(times[i])
                else:
                    if times[i] - peaks[-1] > 0.4:
                        peaks.append(times[i])

    if len(peaks) < 2:
        return 0

    total_interval = 0
    count = 0

    for i in range(1, len(peaks)):
        total_interval += peaks[i] - peaks[i - 1]
        count += 1

    if count == 0:
        return 0

    ave_interval = total_interval / count

    if ave_interval <= 0:
        return 0

    bpm = 60 / ave_interval

    if bpm < 40 or bpm > 180:
        return 0

    return round(bpm, 1)


def get_average(data):
    total = 0
    count = 0

    for d in data:
        if d > 0:
            total += d
            count += 1

    if count == 0:
        return 0

    return round(total / count, 1)


def get_max(data):
    valid = []

    for d in data:
        if d > 0:
            valid.append(d)

    if len(valid) == 0:
        return 0

    return round(max(valid), 1)


def get_result():
    rest_ave = get_average(rest_bpm)
    breath_ave = get_average(breath_bpm)
    max_value = get_max(rest_bpm + breath_bpm)

    diff = 0

    if rest_ave > 0 and breath_ave > 0:
        diff = round(rest_ave - breath_ave, 1)

    if started == False:
        status = "BOOTSELボタンを押すと計測を開始します"
        elapsed = 0
    elif finished == True:
        status = "計測終了"
        elapsed = TOTAL_TIME
    else:
        now = time.ticks_ms()
        elapsed = round(time.ticks_diff(now, start_time) / 1000, 1)

        if elapsed < REST_TIME:
            status = "安静状態を測定中"
        elif elapsed < TOTAL_TIME:
            status = "呼吸誘導中"
        else:
            status = "計測終了"

    result = {
        "status": status,
        "elapsed": elapsed,
        "current_bpm": current_bpm,
        "rest_avg": rest_ave,
        "breath_avg": breath_ave,
        "max_bpm": max_value,
        "diff": diff
    }

    return result


def make_html():
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pulse Result</title>
<style>
body {
    font-family: Arial;
    background-color: #f5f5f5;
    margin: 20px;
}
.box {
    background-color: white;
    padding: 20px;
    border-radius: 10px;
}
h1, h2 {
    text-align: center;
}
.item {
    font-size: 22px;
    margin: 15px;
    padding: 10px;
    border-bottom: 1px solid #ddd;
}
.value {
    font-weight: bold;
    color: #2196F3;
}
</style>
</head>

<body>
<div class="box">
<h1>Pulse Relaxation System</h1>
<h2>脈波センサを用いた呼吸誘導型リラックス支援システム</h2>

<div class="item">状態：<span class="value" id="status">--</span></div>
<div class="item">経過時間：<span class="value" id="elapsed">--</span> 秒</div>
<div class="item">現在の心拍：<span class="value" id="current_bpm">--</span> BPM</div>
<div class="item">呼吸誘導前の平均心拍：<span class="value" id="rest_avg">--</span> BPM</div>
<div class="item">呼吸誘導後の平均心拍：<span class="value" id="breath_avg">--</span> BPM</div>
<div class="item">最大心拍：<span class="value" id="max_bpm">--</span> BPM</div>
<div class="item">前後の平均心拍差：<span class="value" id="diff">--</span> BPM</div>
</div>

<script>
function updateData() {
    fetch("/data")
    .then(response => response.json())
    .then(data => {
        document.getElementById("status").textContent = data.status;
        document.getElementById("elapsed").textContent = data.elapsed;
        document.getElementById("current_bpm").textContent = data.current_bpm;
        document.getElementById("rest_avg").textContent = data.rest_avg;
        document.getElementById("breath_avg").textContent = data.breath_avg;
        document.getElementById("max_bpm").textContent = data.max_bpm;
        document.getElementById("diff").textContent = data.diff;
    });
}

setInterval(updateData, 1000);
updateData();
</script>
</body>
</html>
"""
    return html


def send_response(client, request):
    if "GET /data" in request:
        data = json.dumps(get_result())

        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n"
            "Connection: close\r\n\r\n"
            + data
        )

    else:
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=UTF-8\r\n"
            "Connection: close\r\n\r\n"
            + make_html()
        )

    client.send(response.encode())
    client.close()


connect_wifi()

addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(1)
s.settimeout(0.01)

print("Server started")

while True:
    try:
        client, addr = s.accept()
        request = client.recv(1024).decode()
        send_response(client, request)

    except OSError:
        pass

    if started == False:
        if rp2.bootsel_button() == 1:
            blink_board_led()

            started = True
            finished = False

            data_list = []
            rest_bpm = []
            breath_bpm = []

            start_time = time.ticks_ms()
            last_sample_time = start_time
            last_bpm_time = start_time
            smooth_value = read_pulse()
            breath_start = False
            current_bpm = 0

            print("START")

    else:
        if finished == False:
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, start_time) / 1000

            if elapsed >= REST_TIME and breath_start == False:
                breath_led.duty_u16(0)
                blink_board_led()
                breath_start = True

            if elapsed > TOTAL_TIME:
                breath_led.duty_u16(0)
                blink_board_led()

                finished = True

                rest_ave = get_average(rest_bpm)
                breath_ave = get_average(breath_bpm)
                max_value = get_max(rest_bpm + breath_bpm)

                diff = 0
                if rest_ave > 0 and breath_ave > 0:
                    diff = round(rest_ave - breath_ave, 1)

                print("END")
                print("呼吸誘導前の平均心拍:", rest_ave, "BPM")
                print("呼吸誘導後の平均心拍:", breath_ave, "BPM")
                print("最大心拍:", max_value, "BPM")
                print("前後の平均心拍差:", diff, "BPM")

            if time.ticks_diff(now, last_sample_time) >= SAMPLE_TIME:
                pulse = read_pulse()
                smooth_value = alpha * pulse + (1 - alpha) * smooth_value

                status = breath_led_control(elapsed)

                data_list.append([round(elapsed, 2), smooth_value])

                if len(data_list) > 500:
                    data_list.pop(0)

                if time.ticks_diff(now, last_bpm_time) >= 1000:
                    current_bpm = get_bpm(data_list)

                    if current_bpm > 0:
                        if elapsed < REST_TIME:
                            rest_bpm.append(current_bpm)
                        elif elapsed < TOTAL_TIME:
                            breath_bpm.append(current_bpm)

                    print("DATA,{:.2f},{:.4f},{},{}".format(
                        elapsed,
                        smooth_value,
                        current_bpm,
                        status
                    ))

                    last_bpm_time = now

                last_sample_time = now

