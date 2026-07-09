import re

with open(r'C:\Users\xlong\AppData\Local\Temp\codecs.xml', 'r', encoding='utf-8') as f:
    xml = f.read()

for m in re.finditer(r'<MediaCodec name="([^"]+)" type="([^"]+)"', xml):
    name, typ = m.group(1), m.group(2)
    is_enc = 'encoder' in name.lower()
    label = 'ENC' if is_enc else 'DEC'
    print(f'  [{label}] {name}')
    print(f'        type: {typ}')
    print()
