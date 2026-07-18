#!/bin/bash
set -e

BUSYBOX_DIR=/home/xlong/v3s/buildroot-2024.02/output/build/busybox-1.36.1
echo "=== Entering $BUSYBOX_DIR ==="
cd "$BUSYBOX_DIR"

# .config may be a symlink in Buildroot — resolve it
if [ -L .config ]; then
    REAL_CONFIG=$(readlink -f .config)
    echo ".config is a symlink -> $REAL_CONFIG"
    rm .config
    cp "$REAL_CONFIG" .config
fi

# Enable CONFIG_STATIC
sed -i 's|# CONFIG_STATIC is not set|CONFIG_STATIC=y|' .config
grep CONFIG_STATIC .config | head -5

# Non-interactive oldconfig
echo "=== Running oldconfig ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- oldconfig 2>&1 | tail -5

echo "=== Building static busybox ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc) 2>&1 | tail -10

echo "=== Verify static binary ==="
file busybox
ls -lh busybox

# Copy to project
cp busybox /mnt/c/my_project/TUN_NAT_HUB/backup/busybox_static
echo "=== Done! busybox_static saved ==="
