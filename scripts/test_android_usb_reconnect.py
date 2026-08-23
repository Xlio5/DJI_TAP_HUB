from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "tunnathub" / "app" / "service" / "TunNatVpnService.kt"


def test_started_but_disconnected_start_command_kicks_reconnect():
    text = SERVICE.read_text(encoding="utf-8")
    marker = "VPN 服务在但隧道未连"
    start = text.index(marker)
    end = text.index("isStarted = true", start)
    branch = text[start:end]
    assert "reconnectScope.launch { doReconnect() }" in branch
    assert "return START_STICKY" in branch


if __name__ == "__main__":
    test_started_but_disconnected_start_command_kicks_reconnect()
    print("android_usb_reconnect=OK")
