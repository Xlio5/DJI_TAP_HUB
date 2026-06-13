#!/bin/bash
# setup_gadget.sh - Load g_serial (Pure Bulk mode)
# Impersonates RTL8812AU VID/PID to bypass DJI RC USB whitelist
set -e

if [ -c /dev/ttyGS0 ]; then
    echo "g_serial already ready (/dev/ttyGS0)"
    exit 0
fi

echo "=== Loading g_serial Gadget (RTL8812AU VID/PID) ==="

modprobe -r g_serial 2>/dev/null || true
sleep 1
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812
sleep 2

if [ -c /dev/ttyGS0 ]; then
    chmod 666 /dev/ttyGS0 2>/dev/null || true
    echo "g_serial loaded: /dev/ttyGS0"
else
    echo "WARNING: /dev/ttyGS0 not found"
fi
