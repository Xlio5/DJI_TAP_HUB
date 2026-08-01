from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "tunnathub" / "app" / "MainActivity.kt"


class AndroidRcStatusContractTest(unittest.TestCase):
    def test_left_nav_has_remote_tab(self):
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("private enum class Tab { VIDEO, REMOTE, CONFIG }", src)
        self.assertIn("selectedTab = Tab.REMOTE", src)

    def test_remote_view_uses_sbus_range_and_raw_channels(self):
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("RcPanelContent(", src)
        self.assertIn("for (rowStart in 1..16 step 2)", src)
        self.assertIn("raw_ch", src)
        self.assertIn("1500", src)
        self.assertIn("1000f", src)
        self.assertIn("2000f", src)

    def test_rc_polling_runs_at_50ms(self):
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("kotlinx.coroutines.delay(50)", src)

    def test_remote_view_shows_switch_and_button_groups(self):
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("ModeSwitch(", src)
        self.assertIn("\"S\"", src)
        self.assertIn("\"N\"", src)
        self.assertIn("\"F\"", src)
        self.assertIn("ButtonStatusGrid(", src)

    def test_speed_polling_has_stats_fallback(self):
        src = MAIN.read_text(encoding="utf-8")
        self.assertIn("/api/stats", src)
        self.assertIn("calcMbps", src)
        self.assertIn("bandwidth_mbps", src)


if __name__ == "__main__":
    unittest.main()
