from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "tunnathub" / "app" / "MainActivity.kt"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v3s_rcmsg_receiver_is_not_recreated_on_input_mode_switch():
    text = read(MAIN)
    assert "currentRcInputMode" in text
    assert "LaunchedEffect(vpnRunning) {" in text
    assert "LaunchedEffect(vpnRunning, rcInputMode)" not in text


def test_v3s_rcmsg_receiver_uses_latest_input_mode_inside_loop():
    text = read(MAIN)
    start = text.index("// ── RC 遥控器数据: 直接收 UDP rcmsg")
    end = text.index("fun togglePlay()", start)
    body = text[start:end]
    assert "currentRcInputMode" in body
    assert "rcInputMode == RcInputMode.V3S_RCMSG" not in body
    assert "rcChannelsForIncomingData(rcChs, data.chs, currentRcInputMode" in body


def test_v3s_rcmsg_receiver_exits_quickly_when_cancelled():
    text = read(MAIN)
    start = text.index("// ── RC 遥控器数据: 直接收 UDP rcmsg")
    end = text.index("fun togglePlay()", start)
    body = text[start:end]
    assert "sock.soTimeout = 100" in body
    assert "currentCoroutineContext().isActive" in body


if __name__ == "__main__":
    tests = [
        test_v3s_rcmsg_receiver_is_not_recreated_on_input_mode_switch,
        test_v3s_rcmsg_receiver_uses_latest_input_mode_inside_loop,
        test_v3s_rcmsg_receiver_exits_quickly_when_cancelled,
    ]
    for test in tests:
        test()
    print("android_rcmsg_receiver_stability=OK")
