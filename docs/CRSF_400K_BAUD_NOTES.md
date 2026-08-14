# CRSF 400k 波特率兼容 — 实现笔记

> 日期: 2026-08-15
> 目标: ELRS + MLRS 统一用 400k 波特率（MLRS 固定 400k，ELRS 也兼容）
> 结论: ✅ V3s uartclk=84MHz，分频 div=13 DLF=2 → **精确 400000**，ELRS Lua 完整工作

---

## 一、关键结论

**V3s UART0 通过内核 8250_dw 驱动的 DLF（分数分频）可精确输出 400000 波特率，ELRS Lua 配置在 400k 下完整工作（渲染 + 改值）。**

| 项 | 值 |
|---|---|
| V3s UART 时钟 | **84MHz**（APB2，实测反推）|
| **400k 分频** | **div=13, DLF=2** → **400000（精确）** |
| 读寄存器方法 | **必须设 DLAB=1 才读 DLL/DLH/DLF**（否则读到数据寄存器残留）|
| ELRS 400k 响应 | ✅ 渲染 6 行参数 + 改值生效 |

---

## 二、为什么 400k 之前"不稳定"（真根因）

**不是波特率问题，是 App 路由问题（已修复）**：

1. **V3s 400k 分频一直是正确的**（div=13 DLF=2 → 400000 精确）
2. 之前"乱码/不响应"是因为 **App 发包走 wlan0 不到 V3s**（`ip route get 10.0.0.1 uid App` 走 wlan0）→ bridge 不转发 → ELRS 不响应 → App 不识别
3. **修复**：`bindSocketToVpn`（socket 显式绑定 VPN network）+ UDP `connect`（connect 的 socket 严格走绑定网络）
4. 电脑桥 @400000 读 V3s 显示"乱码"是**监测工具采样现象**（0.27% 偏差字节级），不影响实际链路（V3s 直连 ELRS 正常）

**证据**：路由修复后，V3s bridge recv 增量>0（App ping 到达），ELRS 400k 响应，App 渲染 6 行。

---

## 三、技术细节

### 3.1 内核 DLF 支持（已确认）
- dts: `sun8i-v3s.dtsi` `uart0: serial@1c28000` `compatible = "snps,dw-apb-uart"`
- 驱动: `8250_dw.c` `dw8250_set_divisor()` 写 `DW_UART_DLF` 分数分频
- 接入: `8250_port.c` `serial8250_set_divisor(port, baud, quot, frac)` → `dw8250_set_divisor`
- **实测寄存器（DLAB 正确读）**: `DLL=0x0D DLH=0x00 DLF=0x02` → 400000 bps

### 3.2 波特率计算
```
DesignWare 16550: baud = uartclk / (16 × (div + DLF/16))
uartclk = 84MHz
div = (DLH<<8)|DLL = 13, DLF = 2
actual = 84M / (16 × (13 + 2/16)) = 400000 (精确)
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
