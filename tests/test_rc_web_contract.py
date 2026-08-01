from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DJI_RC = ROOT / "ubuntu" / "src" / "dji_rc.cpp"
WEB_SERVER = ROOT / "ubuntu" / "src" / "web_server.cpp"


class RcWebContractTest(unittest.TestCase):
    def test_dji_rc_exports_full_sbus_channel_contract(self):
        src = DJI_RC.read_text(encoding="utf-8")

        for index in range(1, 17):
            self.assertIn(f'\\"ch{index}\\":', src)

        for index in range(1, 7):
            self.assertIn(f'\\"raw_ch{index}\\":', src)

        self.assertIn("chmap_build(&st, ch)", src)

    def test_web_uses_mapped_channel_range_and_all_16_channels(self):
        src = WEB_SERVER.read_text(encoding="utf-8")

        self.assertIn("let mapped=[];", src)
        self.assertIn("1500", src)

        self.assertIn("for(let i=1;i<=16;i++)", src)
        self.assertIn("rc['ch'+i]", src)


if __name__ == "__main__":
    unittest.main()
