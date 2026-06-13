"""Test if DJI RC UsbManager.openDevice() succeeds for our RTL8812AU-impersonating gadget."""
import subprocess, time

adb = "adb"
dev = "172.24.91.112:46561"

subprocess.run([adb, "connect", dev], capture_output=True, timeout=5)

# Get detailed USB descriptors for our device
print("=== USB Descriptors ===")
r = subprocess.run([adb, "-s", dev, "shell", "cat /sys/bus/usb/devices/4-1/descriptors 2>/dev/null | xxd | head -60"],
                  capture_output=True, text=True, timeout=10)
print(r.stdout)

# Check if there's an existing permission for this VID/PID
print("=== Permissions ===")
r = subprocess.run([adb, "-s", dev, "shell", "dumpsys usb 2>&1 | grep -A20 permissions_manager"],
                  capture_output=True, text=True, timeout=10)
print(r.stdout)

# Check what interfaces our device has
print("=== Interface info ===")
r = subprocess.run([adb, "-s", dev, "shell", "cat /sys/bus/usb/devices/4-1/4-1:1.0/bInterfaceClass 2>/dev/null; echo ''; cat /sys/bus/usb/devices/4-1/4-1:1.0/bInterfaceSubClass 2>/dev/null"],
                  capture_output=True, text=True, timeout=5)
print("Interface class/subclass:", r.stdout.strip())

# Check our app UID
print("=== Our app ===")
r = subprocess.run([adb, "-s", dev, "shell", "pm list packages | grep tunnathub"],
                  capture_output=True, text=True, timeout=5)
print(r.stdout)
r = subprocess.run([adb, "-s", dev, "shell", "dumpsys package com.tunnathub.app 2>&1 | grep -E 'uid=|userId='" ],
                  capture_output=True, text=True, timeout=10)
print(r.stdout)

print("\nDone")
