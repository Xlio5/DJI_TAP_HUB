#!/bin/sh
# 查证 UART0 引脚配置全链路 — 老大要的配置核查
echo '=== 3. U-Boot 侧 DTS uart0 ==='
UDTS=$(find /home/xlong/v3s/u-boot -path '*allwinner/sun8i-v3s-licheepi-zero.dts' | head -1)
echo "文件: $UDTS"
grep -A5 '&uart0' "$UDTS"

echo ''
echo '=== 4. 内核 dock.dts 开头(确认 include 关系)==='
head -30 /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts

echo ''
echo '=== 4b. dock.dts 里是否有 uart/mmc 覆盖 ==='
grep -n 'uart\|mmc' /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts

echo ''
echo '=== 6. 全源码树搜索:有没有任何地方把 uart0 配到 PF ==='
grep -rn 'uart0' /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s.dtsi | grep -i 'pf' || echo '(内核 dtsi: 无 PF 上的 uart0 定义)'
grep -rn 'PF2\|PF4' /home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s*.dts* | grep -i uart || echo '(内核 DTS: PF2/PF4 无 uart 引用)'
