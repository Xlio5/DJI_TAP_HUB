from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DJI_RC = ROOT / "ubuntu" / "src" / "dji_rc.cpp"
S99 = ROOT / "ubuntu" / "scripts" / "S99tun_nat_hub"


class V3sRcmsgContractTest(unittest.TestCase):
    def test_dji_rc_has_fixed_udp_rcmsg_sender(self):
        src = DJI_RC.read_text(encoding="utf-8")
        self.assertIn("RCMSG_PORT = 65530", src)
        self.assertIn("RCMSG_MAGIC", src)
        self.assertIn("send_rcmsg", src)
        self.assertIn("sendto(", src)
        self.assertIn("10.0.0.2", src)

    def test_startup_enables_fixed_rcmsg_port_and_50hz_interval(self):
        src = S99.read_text(encoding="utf-8")
        self.assertIn("--rcmsg-host 10.0.0.2", src)
        self.assertIn("--rcmsg-port 65530", src)
        self.assertIn("--interval 20", src)


if __name__ == "__main__":
    unittest.main()
