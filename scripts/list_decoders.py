"""List all available video decoders on connected ADB device"""
import subprocess, re

result = subprocess.run(
    ["adb", "shell", "dumpsys", "media.codec"],
    capture_output=True, text=True
)
text = result.stdout

# Find all decoders for video/avc (H.264)
avc = re.findall(r'Decoder\s+"([^"]+)"\s+supports', text)
print("=== All Decoders ===")
for d in avc:
    print(f"  {d}")

# Also check Google C2
result2 = subprocess.run(
    ["adb", "shell", "cat", "/vendor/etc/media_codecs_google_c2_video.xml"],
    capture_output=True, text=True
)
google = re.findall(r'name="(c2\.[^"]+)"', result2.stdout)
print("\n=== Google C2 Video Codecs ===")
for g in google:
    print(f"  {g}")
