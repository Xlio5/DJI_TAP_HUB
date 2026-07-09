"""Query all H.264 decoders available on device via dumpsys"""
import subprocess, re

# Get codec list from XML files
result = subprocess.run(
    ["adb", "shell", "cat /vendor/etc/media_codecs_lahaina_vendor.xml /vendor/etc/media_codecs_google_c2_video.xml /vendor/etc/media_codecs.xml 2>/dev/null"],
    capture_output=True, text=True
)
text = result.stdout

print("=== H.264 (video/avc) Decoders ===")
for m in re.finditer(r'<MediaCodec\s+name="([^"]+)"\s+type="video/avc"', text):
    print(f"  {m.group(1)}")

print("\n=== H.265 (video/hevc) Decoders ===")
for m in re.finditer(r'<MediaCodec\s+name="([^"]+)"\s+type="video/hevc"', text):
    print(f"  {m.group(1)}")

# Also try running a small query on device
print("\n=== Runtime check ===")
r2 = subprocess.run(
    ["adb", "shell", "for f in /vendor/etc/media_codecs*.xml; do echo \"--- \$f ---\"; grep -oP 'name=\"c2\.[^\"]*avc[^\"]*\"' \"\$f\" 2>/dev/null; done"],
    capture_output=True, text=True
)
print(r2.stdout)
