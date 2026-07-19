#!/usr/bin/env python3
import os,zlib,struct
PROJECT='/mnt/c/my_project/TUN_NAT_HUB'
TGT='/home/xlong/v3s/buildroot-2024.02/output/target'
CPP=PROJECT+'/ubuntu/src/web_server.cpp'
orig_ver='"1.3.1"'

print("=== Compile web_server (flash_erase fix) ===")
ws=TGT+'/usr/local/bin/web_server'
os.system('arm-linux-gnueabihf-g++ -std=c++17 -Os -o '+ws+' '+CPP+' -lpthread 2>&1 | tail -2')
os.chmod(ws,0o755)
fl=os.popen('strings '+ws).read().count('flash_erase')
print('flash_erase refs:',fl)

print("=== Build rootfs + SPI ===")
os.chdir('/home/xlong/v3s/buildroot-2024.02')
os.system('mksquashfs output/target /tmp/r.sq -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3')
data=open('/tmp/r.sq','rb').read()
crc=zlib.crc32(data)&0xFFFFFFFF
open(PROJECT+'/backup/rootfs.squashfs','wb').write(data+b'TUN_NAT_HUB'+struct.pack('<I',crc))
print('rootfs: %d bytes' % (len(data)+12))

os.chdir(PROJECT)
os.system('python3 -B scripts/build_spi_final.py 2>&1 | tail -4')

print("=== v1.4.1 ===")
src=open(CPP).read()
src=src.replace(orig_ver,'"1.4.1"')
open(CPP,'w').write(src)
os.system('arm-linux-gnueabihf-g++ -std=c++17 -Os -o '+ws+' '+CPP+' -lpthread 2>&1 | tail -2')
os.system('cd /home/xlong/v3s/buildroot-2024.02 && mksquashfs output/target /tmp/r141.sq -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3')
data=open('/tmp/r141.sq','rb').read()
crc=zlib.crc32(data)&0xFFFFFFFF
open(PROJECT+'/backup/rootfs_v141.squashfs','wb').write(data+b'TUN_NAT_HUB'+struct.pack('<I',crc))
print('v1.4.1: %d bytes' % (len(data)+12))

print("=== v1.4.2 ===")
src=open(CPP).read()
src=src.replace('"1.4.1"','"1.4.2"')
open(CPP,'w').write(src)
os.system('arm-linux-gnueabihf-g++ -std=c++17 -Os -o '+ws+' '+CPP+' -lpthread 2>&1 | tail -2')
os.system('cd /home/xlong/v3s/buildroot-2024.02 && mksquashfs output/target /tmp/r142.sq -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3')
data=open('/tmp/r142.sq','rb').read()
crc=zlib.crc32(data)&0xFFFFFFFF
open(PROJECT+'/backup/rootfs_v142.squashfs','wb').write(data+b'TUN_NAT_HUB'+struct.pack('<I',crc))
print('v1.4.2: %d bytes' % (len(data)+12))

src=open(CPP).read()
src=src.replace('"1.4.2"',orig_ver)
open(CPP,'w').write(src)
print("DONE")
