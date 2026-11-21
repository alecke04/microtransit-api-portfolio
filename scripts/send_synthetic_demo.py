"""Send generated points only to the loopback demo server, never to a production URL."""

import math
import time

import httpx

from app.config import get_settings


def main():
    settings = get_settings()
    device, key = next(iter(settings.device_keys().items()))
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        registered = client.post(
            "/api/devices",
            headers={"X-API-Key": key},
            json={"device_id": device, "team_name": "Synthetic demo", "api_key": key},
        )
        if registered.status_code not in {201, 409}:
            raise SystemExit("Demo registration failed")
        for step in range(12):
            response = client.post(
                "/api/locations",
                headers={"X-API-Key": key},
                json={
                    "device_id": device,
                    "latitude": round(0.01 * math.sin(step / 12 * math.tau), 6),
                    "longitude": round(0.01 * math.cos(step / 12 * math.tau), 6),
                    "speed": 4,
                    "accuracy": 3,
                    "fix_status": 1,
                    "timestamp": int(time.time() * 1000),
                },
            )
            if response.status_code != 201:
                raise SystemExit(f"Demo point failed ({response.status_code}); inspect locally before retrying")
            print(f"Synthetic point {step + 1}/12 saved")
            time.sleep(2.1)


if __name__ == "__main__":
    main()
