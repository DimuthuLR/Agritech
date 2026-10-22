# ============================================================
# AgriTech — WiFi Manager
# ============================================================

import network
import time

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    raise RuntimeError("secrets.py not found")


_wlan = None


def _get_wlan():
    global _wlan
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
        _wlan.active(True)
    return _wlan


def is_connected():
    return _get_wlan().isconnected()


def get_ip():
    return _get_wlan().ifconfig()[0]


def get_rssi():
    wlan = _get_wlan()
    if not wlan.isconnected():
        return None
    return wlan.status("rssi")


def connect(timeout_sec=20):
    wlan = _get_wlan()
    if wlan.isconnected():
        print(f"[wifi] Already connected, IP={wlan.ifconfig()[0]}")
        return True

    print(f"[wifi] Connecting to '{WIFI_SSID}'...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    for _ in range(timeout_sec * 2):
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            rssi = wlan.status("rssi")
            print(f"[wifi] Connected, IP={ip}, RSSI={rssi}dBm")
            return True
        time.sleep(0.5)

    status = wlan.status()
    print(f"[wifi] FAILED after {timeout_sec}s (status={status})")
    return False


def disconnect():
    wlan = _get_wlan()
    wlan.disconnect()
    print("[wifi] Disconnected")