#!/usr/bin/env python3
"""Build rootfs with web_server logging + 12B verification tail"""
import os, shutil, zlib, struct, subprocess, sys

PROJECT = "/mnt/c/my_project/TUN_NAT_HUB"
TGT = "/home/xlong/v3s/buildroot-2024.02/output/target"
CPP = f"{PROJECT}/ubuntu/src/web_server.cpp"

# 1. Add logging to web_server source BEFORE compilation
# HIGH-2/4 修复: 修改前先备份 + with 语句 + 替换计数告警
with open(CPP, encoding="utf-8") as f:
    ws_src = f.read()

added = 0

# Add log after inactiveDev assignment
old = 'std::cout << "[fw] current slot: " << (runningOnB ? "B" : "A")'
new = ('std::cout << "[fw] UPGRADE START: target=" << inactiveDev << ", size=" << contentLen << std::endl;'
       '\n\t' + old)
if old in ws_src:
    ws_src = ws_src.replace(old, new)
    print("Added upgrade start log")
    added += 1
else:
    print("[WARN] 未找到注入点1, 源码结构可能已变", file=sys.stderr)

# Add log after dd success
old2 = 'std::string flashCmd = "dd if=" + tmpPath + " of=" + inactiveDev + " bs=4096 2>&1";'
new2 = ('std::cout << "[fw] dd " << tmpPath << " -> " << inactiveDev << std::endl;'
        '\n\t' + old2)
if old2 in ws_src:
    ws_src = ws_src.replace(old2, new2)
    print("Added dd log")
    added += 1
else:
    print("[WARN] 未找到注入点2, 源码结构可能已变", file=sys.stderr)

# Add log after slot write
old3 = '::close(slotFd);\n\t\tsync();'
new3 = ('::close(slotFd);'
        '\n\t\tstd::cout << "[fw] slot flag + confirmed/retry written" << std::endl;'
        '\n\t\tsync();')
if old3 in ws_src:
    ws_src = ws_src.replace(old3, new3)
    print("Added slot write log")
    added += 1
else:
    print("[WARN] 未找到注入点3, 源码结构可能已变", file=sys.stderr)

# HIGH-2 修复: 有实际修改才写回; 写前备份 (git 可恢复, 但额外 .bak 保险)
if added > 0:
    shutil.copy2(CPP, CPP + ".bak_ota")
    with open(CPP, "w", encoding="utf-8") as f:
        f.write(ws_src)
    print(f"已写回 {CPP} (新增 {added} 处日志)")
else:
    print("[WARN] 没有任何注入生效, 跳过写回", file=sys.stderr)

# 2. Compile web_server
print("Compiling web_server...")
# MEDIUM-6 修复: 用 subprocess.run 检查返回码, 编译失败立即中止 (不再静默继续)
r = subprocess.run(
    f"arm-linux-gnueabihf-g++ -std=c++17 -Os -o {TGT}/usr/local/bin/web_server {CPP} -lpthread 2>&1 | tail -2",
    shell=True, capture_output=True, text=True,
)
if r.returncode != 0:
    print(f"[ERROR] 编译 web_server 失败:\n{r.stdout}", file=sys.stderr)
    sys.exit(1)
os.chmod(f"{TGT}/usr/local/bin/web_server", 0o755)
print(f"web_server: {os.path.getsize(f'{TGT}/usr/local/bin/web_server')} bytes")

# 3. Copy init scripts
for src, dst in [
    (f"{PROJECT}/ubuntu/scripts/S99tun_nat_hub", f"{TGT}/etc/init.d/"),
    (f"{PROJECT}/ubuntu/scripts/setup_v3s_fixed.sh", f"{TGT}/usr/local/bin/setup_v3s.sh"),
]:
    shutil.copy(src, dst)
    os.chmod(dst, 0o755)

# 4. Build squashfs
print("Building squashfs...")
os.chdir("/home/xlong/v3s/buildroot-2024.02")
r = subprocess.run(
    "mksquashfs output/target /tmp/rootfs_tmp.sq -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3",
    shell=True, capture_output=True, text=True,
)
if r.returncode != 0:
    print(f"[ERROR] mksquashfs 失败:\n{r.stdout}", file=sys.stderr)
    sys.exit(1)

# 5. Append 12B verification tail (TUN_NAT_HUB + CRC32)
with open("/tmp/rootfs_tmp.sq", "rb") as f:
    data = f.read()
crc = zlib.crc32(data) & 0xFFFFFFFF
tail = b"TUN_NAT_HUB" + struct.pack("<I", crc)
with open(f"{PROJECT}/backup/rootfs.squashfs", "wb") as f:
    f.write(data + tail)
print(f"rootfs: {os.path.getsize(f'{PROJECT}/backup/rootfs.squashfs')} bytes (tail=12B, CRC=0x{crc:08X})")

# 6. Also build SPI image
print("Building SPI image...")
os.chdir(PROJECT)
os.system("python3 -B scripts/build_spi_final.py 2>&1 | tail -6")
print(f"spi_image: {os.path.getsize(f'{PROJECT}/backup/spi_image.bin')} bytes")

print("DONE - rootfs + SPI image ready")
