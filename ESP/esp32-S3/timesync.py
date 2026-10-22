# ============================================================
# AgriTech — Time sync from server HTTP Date header
#
# Every HTTP response includes a "Date:" header in UTC format
# per RFC 7231. We parse it once at boot and set the ESP32 RTC.
# No timezone handling needed — the server always sends UTC.
# ============================================================

import urequests as requests
import machine
import time

try:
    from secrets import SERVER_URL
except ImportError:
    raise RuntimeError("secrets.py missing")


def sync():
    """
    Fetch the server's Date header and set the RTC to UTC.
    Returns True on success.
    """
    base = SERVER_URL.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[:-7]
    url = base + "/health"

    try:
        resp = requests.get(url, timeout=10)
        date_hdr = resp.headers.get("Date")
        resp.close()
    except Exception as e:
        print(f"[time] HTTP failed: {e}")
        return False

    if not date_hdr:
        print("[time] No Date header in response")
        return False

    # Format: "Sun, 12 Oct 2026 10:30:00 GMT"
    try:
        parts = date_hdr.split()
        day = int(parts[1])
        months = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        month = months[parts[2]]
        year = int(parts[3])
        hh, mm, ss = (int(x) for x in parts[4].split(":"))
        wd_names = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3,
                    "Fri": 4, "Sat": 5, "Sun": 6}
        wd = wd_names.get(parts[0].rstrip(","), 0)

        machine.RTC().datetime((year, month, day, wd, hh, mm, ss, 0))
        print(f"[time] RTC set to UTC: {date_hdr}")
        return True
    except Exception as e:
        print(f"[time] Date parse failed: {e}")
        return False