"""Check video decode capabilities on RK3588."""
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", username="xlong", password="1234", timeout=15)

def sh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(out)
    if err:
        print("E:", err[:300])

print("=== GStreamer ===")
sh("which gst-launch-1.0 2>&1; gst-inspect-1.0 --version 2>&1 | head -2; true")

print()
print("=== GStreamer Rockchip plugins ===")
sh("gst-inspect-1.0 2>&1 | grep -i 'mpp\|rockchip\|rga\|rkv' || echo 'No RK plugins found'; true")

print()
print("=== FFmpeg ===")
sh("which ffmpeg 2>&1; ffmpeg -version 2>&1 | head -2; true")

print()
print("=== Rockchip MPP devices ===")
sh("ls /dev/mpp_service 2>&1; ls /dev/rga 2>&1; ls /dev/dri/card0 2>&1; true")

print()
print("=== v4l2 devices ===")
sh("ls /dev/video* 2>&1; true")
sh("v4l2-ctl --list-devices 2>&1 | head -10; true")

print()
print("=== OpenCV ===")
sh("python3 -c 'import cv2; print(cv2.__version__)' 2>&1; true")

print()
print("=== apt available packages ===")
sh("apt list --installed 2>/dev/null | grep -iE 'gstreamer|ffmpeg|mpp|opencv|rga' | head -15; true")

c.close()
