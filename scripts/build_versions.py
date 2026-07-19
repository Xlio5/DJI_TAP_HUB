#!/usr/bin/env python3
import os, zlib, struct

PROJECT='/mnt/c/my_project/TUN_NAT_HUB'
TGT='/home/xlong/v3s/buildroot-2024.02/output/target'
CPP=PROJECT+'/ubuntu/src/web_server.cpp'
old_ver='"1.3.1"'

for ver in ['1.4.1','1.4.2']:
    print('=== Building v%s ===' % ver)
    c=open(CPP).read()
    c=c.replace(old_ver,'"%s"'%ver)
    open(CPP,'w').write(c)
    os.system('arm-linux-gnueabihf-g++ -std=c++17 -Os -o '+TGT+'/usr/local/bin/web_server '+CPP+' -lpthread 2>&1 | tail -2')
    os.chmod(TGT+'/usr/local/bin/web_server',0o755)
    os.chdir('/home/xlong/v3s/buildroot-2024.02')
    fn=ver.replace('.','')
    tmp='/tmp/r'+fn+'.sq'
    os.system('mksquashfs output/target '+tmp+' -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3')
    data=open(tmp,'rb').read()
    crc=zlib.crc32(data)&0xFFFFFFFF
    out=PROJECT+'/backup/rootfs_v'+fn+'.squashfs'
    open(out,'wb').write(data+b'TUN_NAT_HUB'+struct.pack('<I',crc))
    print('  v%s: %d bytes CRC=0x%08X'%(ver,len(data)+12,crc))
    c=open(CPP).read()
    c=c.replace('"%s"'%ver,old_ver)
    open(CPP,'w').write(c)

print('Done')
for f in ['rootfs_v141.squashfs','rootfs_v142.squashfs']:
    p=PROJECT+'/backup/'+f
    print('  %s: %d bytes'%(f,os.path.getsize(p)))
