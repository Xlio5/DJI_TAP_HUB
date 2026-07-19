# TUN_NAT_HUB V3s 构建文档

## 构建目标一览

| 目标 | 源文件 | 用途 | 输出 |
|------|--------|------|------|
| **web_server** | `ubuntu/src/web_server.cpp` | 嵌入式 Web 配置面板 + OTA 固件升级 | 静态二进制 ~1MB |
| **usb_tund** | `ubuntu/src/main.cpp`, `ubuntu/src/tun_iface.cpp` | TUN/VPN 守护进程 | 动态链接二进制 |
| **rootfs.squashfs** | Buildroot 输出 + overlay | 根文件系统 (XZ squashfs) | ~4.5MB |
| **spi_image.bin** | U-Boot + DTB + zImage + rootfs | 完整 16MB SPI NOR 镜像 | 16MB |

---

## 1. web_server 编译

### 方式 A：直接编译（推荐，用于只改 web_server）

```bash
# WSL 环境下，一条命令：
arm-linux-gnueabihf-g++ -std=c++17 -O2 -s -static -Wall \
    -o web_server \
    ubuntu/src/web_server.cpp \
    -lpthread

# 编译产物: web_server (静态链接, ~1.1MB)
# 放到 rootfs 里的位置: /usr/local/bin/web_server
```

### 方式 B：CMake 交叉编译（用于改 usb_tund + web_server）

```bash
cd ubuntu/
cmake -B build_v3s \
    -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-armv7-linux.cmake \
    -DCMAKE_BUILD_TYPE=Release
cmake --build build_v3s -- -j$(nproc)

# 产物:
#   build_v3s/web_server
#   build_v3s/usb_tund
```

> ⚠️ CMake 产出的 web_server 是动态链接的，需要 Buildroot sysroot 里的 libstdc++.so。
> 直接编译时加 `-static` 更稳妥，不依赖任何 .so。

---

## 2. rootfs.squashfs 打包

```bash
# 步骤 1: 从 buildroot 编译出基础 rootfs，或解包已有
unsquashfs -d /tmp/rootfs_extracted backup/rootfs_v142.squashfs

# 步骤 2: 替换更新的文件
cp /tmp/web_server_new /tmp/rootfs_extracted/usr/local/bin/web_server
cp ubuntu/scripts/S99tun_nat_hub /tmp/rootfs_extracted/etc/init.d/S99tun_nat_hub

# 步骤 3: 重新打包 (XZ 压缩, all-root)
mksquashfs /tmp/rootfs_extracted backup/rootfs.squashfs \
    -comp xz -noappend -all-root
```

---

## 3. SPI 全量镜像打包

```bash
# 用 Python 脚本从已有 SPI 镜像替换 rootfs 部分
# 保留 U-Boot/DTB/zImage 不变，只换 squashfs
python3 scripts/make_spi_image.py

# OR: 手动构建
python3 -c "
SPI_SIZE = 16*1024*1024
with open('backup/old_spi.bin','rb') as f: old = f.read()
with open('backup/rootfs.squashfs','rb') as f: new_sq = f.read()
offset = old.find(b'hsqs')  # squashfs magic
img = bytearray(old[:offset]) + new_sq
img.extend([0xFF]*(SPI_SIZE-len(img)))
with open('backup/spi_image.bin','wb') as f: f.write(bytes(img))
"
```

---

## 4. 部署方式

### Web 升级（推荐，不需要 FEL）

1. V3s 正常启动 → `http://192.168.144.66:8080`
2. 固件升级区域 → 选择 `backup/rootfs.squashfs`
3. 点击「⬆ 升级」→ 自动 flash_erase + dd 写入 + SPL 标记
4. `reboot` 重启到新版本

### FEL 全量刷写

```bash
# 短接 SPI FLASH MOSI+GND 进 FEL 模式
wsl -u root sunxi-fel spiflash-write 0 backup/spi_image.bin
```

---

## 5. 版本号管理

**单一真相源：** `ubuntu/src/web_server.cpp:36`

```cpp
#define VERSION "1.4.2"   // 改这里
```

**同步位置：**
- `ubuntu/scripts/S99tun_nat_hub:10` — 启动日志
- `docs/CHANGELOG.md` — 变更记录

---

## 6. 每次发布检查清单

- [ ] web_server VERSION 已更新
- [ ] S99tun_nat_hub 启动日志版本同步
- [ ] `arm-linux-gnueabihf-g++ -static` 编译通过
- [ ] `strings web_server | grep 1.4.x` 确认版本号
- [ ] `strings web_server | grep flash_erase` 确认 OTA 特性
- [ ] rootfs.squashfs 已重新打包
- [ ] spi_image.bin 已同步重建
- [ ] `git commit` 记录版本 + 二进制
- [ ] 实际刷写验证 `http://192.168.144.66:8080/api/version` 返回正确版本
