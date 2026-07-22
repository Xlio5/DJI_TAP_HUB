#!/bin/bash
TOOLCHAIN=/home/xlong/toolchains/arm-linux-gnueabihf/usr/bin
CC="${TOOLCHAIN}/arm-linux-gnueabihf-gcc"
SRC=/mnt/c/work/tun_-nat_-hub/scripts/flash_write.c
OUT=/tmp/flash_write

"$CC" -static -O2 -Wall -Wextra "$SRC" -o "$OUT" && echo "Build OK" && file "$OUT"
