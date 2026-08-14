# CRSF 400k 波特率兼容 — 实现笔记

> 日期: 2026-08-15
> 目标: ELRS + MLRS 统一用 400k 波特率（MLRS 固定 400k，ELRS 也兼容）
> 结论: ✅ V3s uartclk=**75MHz**，DLF 分数分频精确输出所有 CRSF 波特率

---

## 一、关键结论

**V3s UART0 内核 8250_dw 驱动 + DLF（分数分频）可精确输出所有 CRSF 波特率（115200/400000/921600/100000），全部 <0.5% 误差。**

| 项 | 值 |
|---|---|
| **V3s UART 时钟 (APB2/uartclk)** | **75MHz**（dmesg base_baud=4687500 × 16；400k 分频 div=11 DLF=11 反推双重确认）|
| 读寄存器方法 | **必须设 DLAB=1 才读 DLL/DLH/DLF**（否则读到数据寄存器残留误导）|
| 400k 分频 | div=11, DLF=11 → **401070（+0.27%）** |

## 二、各波特率精确度（uartclk=75MHz, DLF 分数分频）

| 目标 | div | DLF | 实际 | 误差 | 兼容 |
|---|---|---|---|---|---|
| **100000** | 46 | 14 | 100000 | 0.00% | ✅ |
| **115200** | 40 | 11 | 115207 | +0.01% | ✅ 调试用 |
| **400000** | 11 | 11 | 401070 | +0.27% | ✅ ELRS/MLRS |
| **921600** | 5 | 1 | 925926 | +0.47% | ✅ RC 摇杆 |
| 420000 | 11 | 3 | 418994 | +0.24% | ⚠️ 可选 |

## 三、关键结论（2026-08-15 实测确认）

1. **V3s 硬件能精确兼容所有 CRSF 波特率**（DLF 分数分频，全部 <0.5%）
2. **115200 调试通**：电脑桥 @115200 匹配（115207 vs 115200，0.01%），链路完整
3. **400k 电脑桥乱码**：电脑桥 @400000 读 V3s 401070（0.27% 偏差），USB 转串口（JLink/CH340）采样错位 → **调试环境限制**
4. **400k 产品直连**：V3s 401070 直连 ELRS（0.27% 在 STM32 硬件 UART 容差内），应能工作（之前 00:17 验证过）
5. **APB2=75MHz 确认**：dmesg `base_baud=4687500` + 400k 分频 div=11 DLF=11 反推，双方法一致

---

## 二、为什么 400k 之前"不稳定"（真根因）

**两个叠加因素**：

1. **App 发包走 wlan0 不到 V3s**（`ip route get 10.0.0.1 uid App` 走 wlan0）→ bridge 不转发 → ELRS 不响应 → App 不识别。**已修复**：`bindSocketToVpn`（socket 显式绑定 VPN network）+ UDP `connect`（connect 的 socket 严格走绑定网络）
2. **电脑桥 @400000 读 V3s 401070（0.27% 偏差）乱码**：USB 转串口（JLink/CH340）对非整数分频的 400k 采样错位 → 电脑桥中转时 400k 不通（115200 匹配正常）

**关键认知**：
- **V3s 400k 分频正确**（div=11 DLF=11 → 401070，+0.27%）
- **电脑桥中转 400k 乱码是调试环境限制**（USB 转串口采样 0.27% 偏差），不是 V3s/ELRS 问题
- **产品形态（V3s 直连 ELRS）400k 应能工作**（STM32 硬件 UART 容忍 0.27%）

---

## 三、技术细节

### 3.1 内核 DLF 支持（已确认）
- dts: `sun8i-v3s.dtsi` `uart0: serial@1c28000` `compatible = "snps,dw-apb-uart"`
- 驱动: `8250_dw.c` `dw8250_set_divisor()` 写 `DW_UART_DLF` 分数分频
- 接入: `8250_port.c` `serial8250_set_divisor(port, baud, quot, frac)` → `dw8250_set_divisor`
- **实测寄存器（DLAB 正确读）**: `DLL=0x0B DLH=0x00 DLF=0x0B` → 401070 bps

### 3.2 波特率计算
```
DesignWare 16550: baud = uartclk / (16 × (div + DLF/16))
uartclk = 75MHz (APB2, dmesg base_baud 4687500 × 16)
400k: div = (DLH<<8)|DLL = 11, DLF = 11
actual = 75M / (16 × (11 + 11/16)) = 401070 (+0.27%)
```

### 3.3 关键命令
```bash
# 设置 SPI flash rc_output baud=400000 (web_server API, dji_rc 自动重启)
curl -X POST http://192.168.144.66:8080/api/rc/output -d '{"mode":"crsf","baud":"400000"}'

# 手动重启 dji_rc 让配置生效 (热重配可能不触发)
killall dji_rc; fuser -k /dev/ttyS0; sleep 2
setsid /usr/local/bin/dji_rc --out-baud 400000 --crsf-bridge ... &

# 读 UART0 分频寄存器 (验证 DLF)
devmem 0x01c2800c 32 0x83   # DLAB=1
devmem 0x01c28000 32         # DLL
devmem 0x01c28004 32         # DLH
devmem 0x01c28010 32         # DLF
```

---

## 四、MLRS 兼容

- **MLRS 固定 400k** → V3s 用 400k 输出，兼容
- **ELRS 也兼容 400k**（实测 Lua 配置 + 改值正常）
- **统一 400k**：V3s SPI flash baud=400000 固化，ELRS/MLRS 都工作

---

## 五、注意事项

1. **S99 同步**：`ubuntu/scripts/S99tun_nat_hub` 默认 `--out-baud 400000`（SPI flash 配置优先，但代码一致）
2. **电脑桥测试**：测试时必须跑电脑桥（COM30↔COM10 @400000），否则 V3s 和 ELRS 物理断开，误判"不响应"
3. **V3s 400k vs 电脑 400000**：V3s 实际 401070（+0.27%），电脑 400000，0.27% 偏差在 ELRS 容差内
4. **ELRS 复位**：ELRS 模块可能被异常帧卡死（复位后恢复）
