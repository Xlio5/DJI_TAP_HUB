#!/usr/bin/env python3
"""解析 H.264 SPS 获取实际分辨率"""
import subprocess, sys

def read_uev(bitstream, pos):
    """读取无符号指数哥伦布编码"""
    zeros = 0
    while pos < len(bitstream) * 8:
        byte_idx = pos // 8
        bit_idx = 7 - (pos % 8)
        if bitstream[byte_idx] & (1 << bit_idx): break
        zeros += 1; pos += 1
    pos += 1
    val = 0
    for _ in range(zeros):
        byte_idx = pos // 8
        bit_idx = 7 - (pos % 8)
        val = (val << 1) | (1 if bitstream[byte_idx] & (1 << bit_idx) else 0)
        pos += 1
    return val + (1 << zeros) - 1, pos

def read_bits(bitstream, pos, n):
    val = 0
    for _ in range(n):
        byte_idx = pos // 8
        bit_idx = 7 - (pos % 8)
        val = (val << 1) | (1 if bitstream[byte_idx] & (1 << bit_idx) else 0)
        pos += 1
    return val, pos

def parse_sps(nal_data):
    """Parse SPS NAL unit, return (width, height)"""
    pos = 8  # skip nal header byte
    profile_idc, pos = read_bits(nal_data, pos, 8)
    constraint_flags, pos = read_bits(nal_data, pos, 8)
    level_idc, pos = read_bits(nal_data, pos, 8)
    seq_param_set_id, pos = read_uev(nal_data, pos)

    if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128):
        chroma_format_idc, pos = read_uev(nal_data, pos)
        if chroma_format_idc == 3:
            separate_colour_plane_flag, pos = read_bits(nal_data, pos, 1)
        bit_depth_luma, pos = read_uev(nal_data, pos)
        bit_depth_chroma, pos = read_uev(nal_data, pos)
        qpprime_y_zero, pos = read_bits(nal_data, pos, 1)
        seq_scaling_present, pos = read_bits(nal_data, pos, 1)
        if seq_scaling_present:
            for i in range(8 if chroma_format_idc != 3 else 12):
                seq_scaling_list_present, pos = read_bits(nal_data, pos, 1)
                if seq_scaling_list_present: pass  # skip scaling list parsing

    log2_max_frame_num, pos = read_uev(nal_data, pos)
    pic_order_cnt_type, pos = read_uev(nal_data, pos)

    if pic_order_cnt_type == 0:
        log2_max_poc_lsb, pos = read_uev(nal_data, pos)
    elif pic_order_cnt_type == 1:
        delta_pic_order_always_zero, pos = read_bits(nal_data, pos, 1)
        offset_for_non_ref_pic, pos = read_uev(nal_data, pos)  # se(v) — use ue for now
        offset_for_top_to_bottom_field, pos = read_uev(nal_data, pos)
        num_ref_frames_in_poc_cycle, pos = read_uev(nal_data, pos)
        for _ in range(num_ref_frames_in_poc_cycle):
            offset_for_ref_frame, pos = read_uev(nal_data, pos)

    num_ref_frames, pos = read_uev(nal_data, pos)
    gaps_allowed, pos = read_bits(nal_data, pos, 1)
    pic_width_mbs, pos = read_uev(nal_data, pos)
    pic_height_map_units, pos = read_uev(nal_data, pos)
    frame_mbs_only, pos = read_bits(nal_data, pos, 1)

    width = (pic_width_mbs + 1) * 16
    height = (2 - frame_mbs_only) * (pic_height_map_units + 1) * 16
    return width, height

# Get NAL data from file
# CRITICAL-4 修复: 用列表参数避免 shell=True 命令注入; 校验 filepath 不含 shell 元字符
if len(sys.argv) < 2:
    print("用法: parse_sps.py <远端文件路径> [adb端口]", file=sys.stderr)
    sys.exit(1)
filepath = sys.argv[1]
port = sys.argv[2] if len(sys.argv) > 2 else "42557"
if not filepath.strip() or any(ch in filepath for ch in ";|&`$()<>"):
    print(f"非法文件路径: {filepath}", file=sys.stderr)
    sys.exit(1)
if not port.isdigit():
    print(f"非法端口: {port}", file=sys.stderr)
    sys.exit(1)
# 远端 shell 内的 dd 命令本身是白名单固定格式, 仅 filepath 是参数 (已校验)
shell_cmd = f"dd if={filepath} bs=1 count=128 skip=4 2>/dev/null | od -A n -t x1"
result = subprocess.run(
    ["adb", "-s", f"10.248.133.112:{port}", "shell", shell_cmd],
    capture_output=True, text=True, timeout=10,
)
hex_str = result.stdout.strip().replace('\n', ' ').replace('\r', '')
try:
    sps_data = bytes.fromhex(hex_str)
    w, h = parse_sps(sps_data)
    print(f"{sys.argv[1]}: {w}x{h}")
except Exception as e:
    print(f"Parse error: {e}, hex: {hex_str[:80]}")
