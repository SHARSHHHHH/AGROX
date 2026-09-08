"""Standalone sensor simulator — posts readings to the backend like a real
ESP32 would. Useful for demos without hardware.

Usage:
    python simulate.py                       # normal scenario, ESP32-001
    python simulate.py --scenario dry_soil   # dry soil
    python simulate.py --device ESP32-002 --interval 5

Scenarios: normal | dry_soil | heavy_rain | low_water | high_temp
"""
import argparse
import random
import time
import urllib.request
import json

SCENARIOS = {
    "normal":     {"soil": (35, 55), "temp": (26, 32), "hum": (55, 70), "water": (55, 85)},
    "dry_soil":   {"soil": (12, 24), "temp": (33, 38), "hum": (30, 45), "water": (40, 70)},
    "heavy_rain": {"soil": (60, 80), "temp": (24, 28), "hum": (80, 95), "water": (80, 100)},
    "low_water":  {"soil": (30, 45), "temp": (30, 35), "hum": (50, 65), "water": (5, 18)},
    "high_temp":  {"soil": (20, 35), "temp": (37, 42), "hum": (25, 40), "water": (45, 75)},
}


def reading(device_id, scenario):
    s = SCENARIOS[scenario]
    return {
        "device_id": device_id,
        "soil_moisture": round(random.uniform(*s["soil"]), 1),
        "temperature": round(random.uniform(*s["temp"]), 1),
        "humidity": round(random.uniform(*s["hum"]), 1),
        "water_level": round(random.uniform(*s["water"]), 1),
        "water_flow": round(random.uniform(0, 2), 2),
    }


def post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/api/iot/sensor-data")
    ap.add_argument("--device", default="ESP32-001")
    ap.add_argument("--scenario", default="normal", choices=list(SCENARIOS))
    ap.add_argument("--interval", type=float, default=10)
    ap.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = ap.parse_args()

    print(f"Posting {args.scenario} readings for {args.device} -> {args.url}")
    n = 0
    while args.count == 0 or n < args.count:
        payload = reading(args.device, args.scenario)
        try:
            resp = post(args.url, payload)
            print(f"  sent soil={payload['soil_moisture']}% "
                  f"temp={payload['temperature']}C -> {resp.get('status')}")
        except Exception as e:
            print(f"  error: {e} (is the backend running?)")
        n += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
