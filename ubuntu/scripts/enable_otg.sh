#!/bin/bash
# enable_otg.sh — 为 rock-5c 启用 USB-C OTG (Device/Gadget) 模式
# 通过创建 DTB overlay 实现
set -e

echo "=== 查找当前 DWC3 dr_mode ==="
dtc -I dtb -O dts /boot/dtb/rockchip/rk3588s-rock-5c.dtb 2>/dev/null > /tmp/rock5c_current.dts
grep -A5 -B2 "dr_mode" /tmp/rock5c_current.dts | head -30

echo ""
echo "=== 检查 usbdrd3_0 target ==="
# 找 fc000000.usb 对应的 DWC3 节点
grep -B20 "fc000000.usb" /tmp/rock5c_current.dts | grep "usb@" | head -5
grep -A30 "usbdrd3_0" /tmp/rock5c_current.dts | grep -E "usb@|dwc3@|dr_mode" | head -10

echo ""
echo "=== 创建 OTG overlay ==="
# 目标节点: usbdrd3_0 下面的 dwc3 子节点
# 需要确认正确的 target-path
cat > /tmp/rock-5c-usb-otg.dts << 'DTS'
/dts-v1/;

/ {
    metadata {
        title = "Enable USB-C OTG peripheral mode for ROCK 5C";
        compatible = "radxa,rock-5c", "rockchip,rk3588s";
        category = "misc";
        description = "Set USB-C port DWC3 to peripheral mode for USB gadget";
    };

    fragment@0 {
        target-path = "/usbdrd3_0/usb@fc000000";
        __overlay__ {
            dr_mode = "peripheral";
            status = "okay";
        };
    };
};
DTS

dtc -I dts -O dtb -o /tmp/rock-5c-usb-otg.dtbo /tmp/rock-5c-usb-otg.dts 2>&1 && echo "DTBO编译成功" || echo "DTBO编译失败"
