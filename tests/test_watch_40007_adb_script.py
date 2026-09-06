import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "watch_40007_adb.ps1"


class Watch40007AdbScriptTest(unittest.TestCase):
    def test_watch_40007_adb_script_exists(self):
        self.assertTrue(SCRIPT.exists())

    def test_watch_40007_adb_script_uses_existing_monitor(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("rc_40007_serial_monitor.py", text)
        self.assertIn("--adb", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("40007", text)

    def test_watch_40007_adb_script_supports_raw_capture(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"tmp"', text)
        self.assertIn("p40007_capture_", text)
        self.assertIn("exec-out", text)
        self.assertIn("toybox", text)
        self.assertIn("nc", text)
        self.assertIn("cmd.exe /d /c", text)
        self.assertIn('> `"$outFile`"', text)


if __name__ == "__main__":
    unittest.main()
