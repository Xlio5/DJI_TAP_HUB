#!/bin/bash
# 全盘备份脚本 — 用 nohup 在后台执行，不受 SSH 超时影响
OUT="/tmp/emmc_full.img.gz"
LOG="/tmp/dd.log"
echo "DD 备份开始 $(date)" > "$LOG"
dd if=/dev/mmcblk0 bs=4M 2>>"$LOG" | gzip -1 > "$OUT" 2>>"$LOG"
echo "DD 备份完成 $(date), size=$(ls -lh $OUT | awk '{print $5}')" >> "$LOG"
