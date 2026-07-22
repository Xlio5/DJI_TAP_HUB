#!/bin/bash
export PATH=/home/xlong/toolchains/arm-linux-gnueabihf/usr/bin:$PATH
export LD_LIBRARY_PATH=/home/xlong/toolchains/arm-linux-gnueabihf/usr/lib/x86_64-linux-gnu:/home/xlong/toolchains/arm-linux-gnueabihf/usr/lib:/home/xlong/toolchains/arm-linux-gnueabihf/lib:$LD_LIBRARY_PATH
CC=arm-linux-gnueabihf-gcc
SRC=/mnt/c/work/tun_-nat_-hub/scripts/flash_write.c
OUT=/tmp/flash_write
$CC -static -O2 -Wall -Wextra "$SRC" -o "$OUT"
echo "Build OK"
file "$OUT"
stat -c "%s bytes" "$OUT"
cp "$OUT" /mnt/c/work/tun_-nat_-hub/backup/flash_write
echo "Copied to backup/"
