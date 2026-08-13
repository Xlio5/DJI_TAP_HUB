# CRSF 真机调试规范（防踩坑记录）

> 2026-08-13 复盘：排查"App CRSF 包没到 V3s"时，走了弯路——以为隧道/路由不通，
> 实际是**没有完成 VPN 授权 + adb 触发连接**，App 根本没建立真实隧道。

## 铁律：adb 操作 App 的完整步骤（少一步都白调）

连上 RC 的 adb（USB 直连）后，**必须按顺序做**：

1. **重启 App**（清残留状态）
   ```
   adb shell am force-stop com.tunnathub.app
   adb shell am start -n com.tunnathub.app/.MainActivity
   ```

2. **处理权限弹窗**（关键！没做 = 隧道没建 = 一切网络排查都白费）
   - VPN 授权弹窗：`uiautomator dump` 找 "确定/OK" 按钮，`input tap` 点击
   - USB 授权弹窗（"允许访问 Gadget Serial"）：同样处理

3. **触发连接**（App 不会自动连，必须点"连接"按钮）
   - `uiautomator dump` 找 "连接" 按钮坐标 → `input tap` 点击

4. **确认隧道建立**（再排查网络）
   ```
   adb shell "ip addr show tun0"        # 应看到 10.0.0.2/24
   adb shell "cat /proc/net/dev | grep tun0"  # rx/tx 增长
   ```

5. **确认 VPN + USB 日志**
   ```
   adb logcat -d | grep -E "TUN 接口|USB 已连接|UsbBridge"
   ```

## 本次教训

- **排查"包没到"前，先确认隧道物理上建立了**（tun0 在、USB 连了、VPN 授权了）
- 我花了很多时间抓包/查路由，结果 App 连隧道都没真正建立（缺 VPN 授权）
- **遇到"网络不通"，第一反应应是"权限/连接步骤完成了吗"，而不是怀疑路由/驱动**

## 验证目标（本次）
- CRSF 模式：App 接收机页 → CrsfBridge → 10.0.0.1:65532 → V3s bridge → UART0 → ELRS
- 成功标志：App Lua 界面加载 ELRS 参数（非 mock），能上下选择 + 改值
