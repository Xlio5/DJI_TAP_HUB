from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fel_quick_flash.ps1"
DOC = ROOT / "docs" / "FEL_FAST_FLASH.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_script_keeps_wsl_alive_and_attaches_fel_usb():
    text = read(SCRIPT)
    assert "Start-Process" in text
    assert "wsl.exe" in text
    assert '"sleep"' in text
    assert '"900"' in text
    assert "usbipd list" in text
    assert "1f3a:efe8" in text
    assert '"usbipd"' in text
    assert '"attach"' in text


def test_script_defaults_to_rootfs_only_and_supports_full_spi():
    text = read(SCRIPT)
    assert "0x710000" in text
    assert "spiflash-write 0x710000" in text
    assert "spiflash-write 0 " in text
    assert "FullSpi" in text
    assert "DryRun" in text
    assert "rootfs-only" in text


def test_script_archives_versioned_outputs_and_manifest():
    text = read(SCRIPT)
    assert "release_" in text
    assert "manifest.md" in text
    assert "rootfs_${Version}_${Timestamp}.squashfs" in text
    assert "spi_image_${Version}_${Timestamp}.bin" in text
    assert "Get-FileHash" in text


def test_script_reads_back_after_write():
    text = read(SCRIPT)
    assert "spiflash-read 0x710000" in text
    assert "readback_rootfs" in text
    assert "readback_spi" in text
    assert "Hash mismatch" in text


def test_methodology_doc_has_decision_table():
    text = read(DOC)
    assert "OTA" in text
    assert "rootfs-only FEL" in text
    assert "Full SPI FEL" in text
    assert "S99tun_nat_hub" in text
    assert "dji_rc" in text
    assert "web_server" in text


if __name__ == "__main__":
    tests = [
        test_script_keeps_wsl_alive_and_attaches_fel_usb,
        test_script_defaults_to_rootfs_only_and_supports_full_spi,
        test_script_archives_versioned_outputs_and_manifest,
        test_script_reads_back_after_write,
        test_methodology_doc_has_decision_table,
    ]
    for test in tests:
        test()
    print("fel_quick_flash=OK")
