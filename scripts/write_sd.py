import os
DISK = r'\\.\PhysicalDrive2'
SRC = r'c:\my_project\TUN_NAT_HUB\backup\u-boot-sunxi-with-spl.bin'
with open(SRC, 'rb') as f:
    data = f.read()
h = data[0:4].hex()
s = data[4:12].decode('ascii','replace')
print('Source: %d bytes' % len(data))
print('SPL magic: %s %s' % (h, s))
try:
    disk = open(DISK, 'r+b')
    disk.seek(8 * 512)
    disk.write(data)
    disk.flush()
    disk.seek(8 * 512)
    verify = disk.read(32)
    disk.close()
    ok = True
    for i in range(32):
        if data[i] != verify[i]:
            ok = False
            break
    print('Write: ' + ('OK' if ok else 'FAIL'))
    print('Verify: ' + verify[0:32].hex())
except Exception as e:
    print('ERROR: ' + str(e))
