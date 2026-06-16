#!/bin/bash
# fix_cold_boot.sh — 修复冷启动后 USB VID 和有线网 DHCP 问题

# 1. Install fixed scripts
echo '1234' | sudo -S cp /home/xlong/setup_gadget.sh /usr/local/bin/setup_gadget.sh
echo '1234' | sudo -S cp /home/xlong/setup_nat.sh /usr/local/bin/setup_nat.sh
echo '1234' | sudo -S chmod 755 /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh
echo '1234' | sudo -S sed -i 's/\r$//' /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh 2>/dev/null

# 2. Fix wired network: remove stale netplan, use NM with autoconnect
echo '1234' | sudo -S rm -f /etc/netplan/01-end1.yaml 2>/dev/null
echo '1234' | sudo -S nmcli connection modify "Profile 1" connection.autoconnect yes 2>/dev/null
echo '1234' | sudo -S nmcli connection modify "Profile 1" ipv4.method auto 2>/dev/null
echo '1234' | sudo -S dhclient -r end1 2>/dev/null
sleep 1
echo '1234' | sudo -S dhclient end1 2>/dev/null
sleep 2

# 3. Reload g_serial with correct VID/PID (0x0BDA:0x8812)
echo '1234' | sudo -S bash /usr/local/bin/setup_gadget.sh

# 4. Restart daemon
echo '1234' | sudo -S systemctl restart tun_nat_hub
sleep 2

# 5. Report
echo "tun_nat_hub: $(systemctl is-active tun_nat_hub)"
echo "VID: $(cat /sys/module/g_serial/parameters/idVendor)"
echo "PID: $(cat /sys/module/g_serial/parameters/idProduct)"
echo "end1: $(ip -br addr show end1)"
echo "ttyGS0: $(ls -la /dev/ttyGS0)"
echo "DONE"
