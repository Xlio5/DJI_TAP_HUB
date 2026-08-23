from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DJI_RC = ROOT / "ubuntu" / "src" / "dji_rc.cpp"
WEB_SERVER = ROOT / "ubuntu" / "src" / "web_server.cpp"
S99 = ROOT / "ubuntu" / "scripts" / "S99tun_nat_hub"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_uart0_getty_is_owned_by_inittab():
    # UART0 debug getty 由 Buildroot inittab 的 ttyS0::respawn 托管 (GENERIC_SERIAL),
    # S99 不得重复拉 getty。此测试防双 getty 回归 (双 getty 抢 ttyS0 会打死 debug 登录)。
    text = read(S99)
    assert "_respawn_uart0_getty" not in text
    assert "/sbin/getty" not in text


def test_dji_rc_never_kills_uart0_debug_console():
    text = read(DJI_RC)
    assert "pb6_grounded" not in text
    assert "pb6_auto_switch" not in text
    assert "debug_uart0_open" not in text
    assert "fuser -k /dev/ttyS0" not in text
    assert "killall getty" not in text
    assert '"/dev/ttyS0"' not in text


def test_web_default_output_device_is_sc16_not_uart0():
    text = read(WEB_SERVER)
    assert 'std::string rcOutDevice = "/dev/ttySC0";' in text


def test_dji_rc_log_is_bounded_in_init_script():
    text = read(S99)
    assert "_run_bounded_log /tmp/dji_rc.log" in text
    assert "> /var/log/dji_rc.log 2>&1 &" not in text


def test_rc_state_has_tmp_runtime_fallback_and_rates():
    text = read(DJI_RC)
    assert "/tmp/rc_state.json" in text
    assert "good1_hz" in text
    assert "good2_hz" in text
    assert "out_hz" in text
    assert "tx_hz" in text
    assert "tx_ok" in text
    assert "tx_err" in text


def test_web_api_reads_tmp_state_before_varlog():
    text = read(WEB_SERVER)
    tmp_pos = text.find('/tmp/rc_state.json')
    log_pos = text.find('/var/log/rc_state.json')
    assert tmp_pos >= 0
    assert log_pos >= 0
    assert tmp_pos < log_pos


def test_crsf_tx_does_not_reapply_tmux_every_frame():
    text = read(DJI_RC)
    start = text.index("static bool tx_write_uart")
    end = text.index("static bool g_crsf_telem", start)
    body = text[start:end]
    assert "aux_tmux_set" not in body


def test_web_exposes_debug_status_for_uart0_getty():
    text = read(WEB_SERVER)
    assert 'p == "/api/debug/status"' in text
    assert "ttyS0" in text
    assert "getty" in text


if __name__ == "__main__":
    tests = [
        test_uart0_getty_is_owned_by_inittab,
        test_dji_rc_never_kills_uart0_debug_console,
        test_web_default_output_device_is_sc16_not_uart0,
        test_dji_rc_log_is_bounded_in_init_script,
        test_rc_state_has_tmp_runtime_fallback_and_rates,
        test_web_api_reads_tmp_state_before_varlog,
        test_crsf_tx_does_not_reapply_tmux_every_frame,
        test_web_exposes_debug_status_for_uart0_getty,
    ]
    for test in tests:
        test()
    print("v3s_debug_baseline=OK")
