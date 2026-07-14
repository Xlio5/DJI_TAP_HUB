"""Wait for U-Boot banner and immediately interrupt, then set env"""
import serial, time

ser = serial.Serial("COM10", 115200, timeout=0.1)

# Login and reboot
time.sleep(0.2)
ser.read(ser.in_waiting)
ser.write(b"\nroot\n")
time.sleep(2)
out = ser.read(ser.in_waiting).decode(errors="replace")
if "Password" in out:
    ser.write(b"root\n")
    time.sleep(1)
    ser.read(ser.in_waiting)

print("Rebooting...")
ser.write(b"reboot -f\n")
time.sleep(1)

# Read continuously, send ctrl-c as soon as we see U-Boot banner
found = False
for i in range(300):
    data = ser.read(ser.in_waiting)
    text = data.decode(errors="replace")

    # Send ctrl-c as soon as we detect U-Boot boot messages
    if "U-Boot SPL" in text or "Trying to boot" in text or "Hit any key" in text:
        ser.write(b"\x03\x03\x03\n\n")
        print("Interrupt signal sent at SPL/boot stage")

    if "=>" in text:
        found = True
        print("Got U-Boot prompt!")
        break

    # Also check autoboot countdown
    if "autoboot" in text.lower():
        ser.write(b"\x03\n")
        print("Interrupt on autoboot")

    time.sleep(0.05)

if not found:
    # Try sending enter to see if we're already at prompt
    ser.write(b"\n")
    time.sleep(0.3)
    out = ser.read(ser.in_waiting).decode(errors="replace")
    if "=>" in out:
        found = True
        print("Got prompt after enter")

if found:
    print("Setting env...")
    bootargs = ("setenv bootargs console=ttyS0,115200 root=/dev/mtdblock4 "
               "rootfstype=squashfs "
               "g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0 "
               "mtdparts=spi32766.0:1M(uboot),64k(dtb),5790k(kernel),-(rootfs)")

    bootcmd = ("setenv bootcmd sf probe 0; "
              "sf read 0x42000000 0x100000 0x4000; "
              "sf read 0x41000000 0x119800 0x5a7888; "
              "bootz 0x41000000 - 0x42000000")

    for cmd in [bootargs, bootcmd, "saveenv"]:
        ser.write((cmd + "\n").encode())
        time.sleep(1)
        out = ser.read(ser.in_waiting).decode(errors="replace")
        print(out.strip()[-60:])

    print("\n=== READY - Power off, remove SD, power on ===")
else:
    print("Didn't get U-Boot prompt. Current output:")
    out = ser.read(ser.in_waiting).decode(errors="replace")
    print(out[-300:])

ser.close()
