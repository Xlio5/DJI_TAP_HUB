#!/usr/bin/env python3
"""构建完整 SPI 固件镜像 (SPL+U-Boot+ENV+DTB+zImage+rootfs+A/B ctl)
用法: python build_spi_image.py <rootfs.squashfs> <输出.bin>
"""
import subprocess, os, struct, hashlib, sys

def wsl_cat(path):
    # 在 WSL 里直接 cat; 在 Windows 里用 wsl 桥接
    if os.path.exists("/home/xlong"):   # 正在 WSL 内
        with open(path, "rb") as f:
            return f.read()
    return subprocess.check_output(["wsl", "bash", "-c", f"cat {path}"])

def crc32(data):
    import binascii
    return binascii.crc32(data) & 0xFFFFFFFF

def main():
    if len(sys.argv) < 3:
        print("用法: build_spi_image.py <rootfs.squashfs> <输出.bin>")
        return 1
    rootfs_path = sys.argv[1]
    out_path = sys.argv[2]

    with open(rootfs_path, "rb") as f:
        squashfs = f.read()

    spl  = wsl_cat("/home/xlong/v3s/u-boot/spl/sunxi-spl.bin")
    uboot = wsl_cat("/home/xlong/v3s/u-boot/u-boot.bin")
    dtb  = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb")
    zimage = wsl_cat("/home/xlong/v3s/linux/arch/arm/boot/zImage")

    print(f"SPL: {len(spl)}B  U-Boot: {len(uboot)}B  DTB: {len(dtb)}B  zImage: {len(zimage)}B  rootfs: {len(squashfs)}B")

    bootargs = ("console=ttyS0,921600 panic=5 sunxi_wdt.nowayout=1 "
                "rootfstype=squashfs rootwait "
                "mtdparts=firmware:1M(uboot),64k(dtb),6M(kernel),4576k(rootfs_a),-(rootfs_b) g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0")
    bootcmd = "bootz 0x41000000 - 0x42000000"
    env_str = "bootargs=" + bootargs + "\0" + "bootcmd=" + bootcmd + "\0"
    env_bytes = env_str.encode().ljust(0x1FFC, b'\0')
    env_bytes += struct.pack('<I', crc32(env_bytes))
    env_bytes = env_bytes.ljust(0x2000, b'\xFF')

    img = bytearray([0xFF] * (16 * 1024 * 1024))
    img[0:len(spl)] = spl
    img[0x8000:0x8000+len(uboot)] = uboot
    env_off = 0x7E000
    img[env_off:env_off+len(env_bytes)] = env_bytes
    dtb_off = 1024 * 1024
    img[dtb_off:dtb_off+len(dtb)] = dtb
    kernel_off = 1088 * 1024
    img[kernel_off:kernel_off+len(zimage)] = zimage
    rootfs_off = 7232 * 1024
    img[rootfs_off:rootfs_off+len(squashfs)] = squashfs
    img[0xFC000] = 0xFF
    img[0xFC004] = 0xFF
    img[0xFC005] = 0

    with open(out_path, "wb") as f:
        f.write(bytes(img))

    assert img[rootfs_off:rootfs_off+4] == b"hsqs", "rootfs magic 错误!"
    print(f"rootfs magic @ 0x{rootfs_off:X}: hsqs OK")
    print(f"保存: {out_path} ({len(img)} bytes)")
    print(f"rootfs md5: {hashlib.md5(squashfs).hexdigest()}")
    print(f"镜像 md5:   {hashlib.md5(bytes(img)).hexdigest()}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
