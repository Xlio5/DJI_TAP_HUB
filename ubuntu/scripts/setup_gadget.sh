#!/bin/bash
# setup_gadget.sh — 配置 USB CDC ACM Gadget
# 在 systemd 服务启动前执行一次
exec /usr/local/bin/setup_acm_gadget.sh
