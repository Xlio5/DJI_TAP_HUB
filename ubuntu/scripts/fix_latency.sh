#!/bin/bash
echo "=== 当前 TUN qlen ==="
ip link show tun_hub | grep qlen

echo ""
echo "=== 当前 tc qdisc ==="
tc -s qdisc show dev tun_hub 2>/dev/null | head -4

echo ""
echo "=== 修复: 降低 TUN 队列 → 10 ==="
ip link set tun_hub txqueuelen 10

echo ""
echo "=== 修复: fq_codel 替换为 pfifo_fast（更低排队延迟）==="
tc qdisc replace dev tun_hub root pfifo limit 10 2>/dev/null

echo ""
echo "=== 确认 ==="
ip link show tun_hub | grep qlen
tc -s qdisc show dev tun_hub | head -4
echo "Done"
