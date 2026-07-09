import re

files = [
    '/vendor/etc/media_codecs_lahaina_vendor.xml',
    '/vendor/etc/media_codecs_google_c2_video.xml',
    '/vendor/etc/media_codecs_google_c2.xml',
]
all_codecs = {}

for f in files:
    result = __import__('subprocess').run(['adb', 'shell', 'cat', f], capture_output=True, text=True)
    if result.returncode != 0:
        continue
    xml = result.stdout
    for m in re.finditer(r'<MediaCodec name="([^"]+)" type="([^"]+)"', xml):
        name, typ = m.group(1), m.group(2)
        if name not in all_codecs:
            all_codecs[name] = typ

print("=" * 60)
print("DJI RC PLUS 2 (Snapdragon 888 / lahaina) 解码器清单")
print("=" * 60)

print("\n--- 视频解码器 (Video Decoders) ---")
for name, typ in sorted(all_codecs.items()):
    if 'decoder' in name.lower() and 'video' in typ:
        lowlat = 'low_latency' in name
        secure = 'secure' in name
        tag = ''
        if lowlat: tag = ' ⚡低延迟'
        if secure: tag = ' 🔒安全'
        print(f"  {name}{tag}")
        print(f"    MIME: {typ}")

print("\n--- 视频编码器 (Video Encoders) ---")
for name, typ in sorted(all_codecs.items()):
    if 'encoder' in name.lower():
        print(f"  {name}")
        print(f"    MIME: {typ}")

print("\n--- 音频编解码器 ---")
for name, typ in sorted(all_codecs.items()):
    if 'audio' in typ.lower() or 'aac' in name.lower() or 'mp3' in name.lower():
        print(f"  {name}")
        print(f"    MIME: {typ}")
