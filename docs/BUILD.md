# TUN_NAT_HUB V3s 构建文档

## 构建环境

| 组件 | 工具链 | 路径 |
|------|--------|------|
| web_server | Buildroot GCC 12.3.0 (arm-buildroot-linux-gnueabihf) | `/home/xlong/v3s/buildroot-2024.02/output/host/bin/` |
| usb_tund | Buildroot GCC 12.3.0 | 同上 |
| rootfs | Buildroot + overlay | `/home/xlong/v3s/buildroot-2024.02/output/target/` |

## 构建目标

| 目标 | 源文件 | 编译方式 | 输出大小 |
|------|--------|----------|----------|
| **web_server** | `ubuntu/src/web_server.cpp` | 静态链接 (glibc 2.38) | ~1.0MB |
| **usb_tund** | `ubuntu/src/main.cpp`, `ubuntu/src/tun_iface.cpp` | CMake + Buildroot | ~18KB |
| **rootfs.squashfs** | Buildroot 输出 + overlay | mksquashfs (xz) | ~4.5MB |
| **spi_image.bin** | U-Boot + DTB + zImage + rootfs | Python 拼接 | 16MB |

---

## 1. web_server 编译

### ⚠️ 重要：必须使用 Buildroot 工具链

ARM 32-bit + 静态链接 glibc 的 `std::thread` 在 Ubuntu 工具链 (glibc 2.31) 下有 NPTL 兼容问题。
**必须使用 Buildroot 工具链** (glibc 2.38，与 V3s 运行环境一致)。

### 编译前源码修改

web_server.cpp 需要做以下适配（已固定于源码）：
1. **不能使用 `std::thread`** — 单线程顺序处理请求
2. **`BwPrev::time` → `ts`** — 避免 GCC 12 `::time()` 冲突
3. **`VERSION` 宏** — 每次发布更新

### 编译命令

```bash
# WSL 环境
/home/xlong/v3s/buildroot-2024.02/output/host/bin/arm-buildroot-linux-gnueabihf-g++ \
    -std=c++17 -Os -s -static -Wall \
    -o web_server \
    ubuntu/src/web_server.cpp \
    -lpthread

# 产物: web_server (1.0MB, statically linked)
```

> `-lpthread` 虽然不用 thread，但 `std::mutex`/`std::call_once` 等 C++ 运行时内部可能用到，保留链接。

---

## 2. rootfs.squashfs 打包

### ⚠️⚠️ 重要：必须从"已验证的 base rootfs"提取 + 替换，禁止用 buildroot target 直接 mksquashfs

**这是踩过的坑（2026-08-13，v1.6.5 构建）**：

| 错误做法 | 后果 |
|---------|------|
| 用 `/home/xlong/v3s/buildroot-2024.02/output/target` 直接 `mksquashfs` | **丢失 setup_v3s.sh 的 172.20.10.3 备用 IP**（target 里是旧版，没同步）。固件烧进去只有 192.168.144.66，172 调试入口没了 |

**正确做法**（用当前最新 base rootfs 提取，保留所有已固化配置，只替换要更新的二进制）：

```bash
# 步骤 0: 选 base —— 用 backup/ 里最新的已验证 rootfs (如 rootfs_v7.squashfs)
BASE=backup/rootfs_v7.squashfs
OUT=/home/xlong/build_v165
rm -rf "$OUT"; mkdir -p "$OUT"
unsquashfs -q -f -d "$OUT" "$BASE"

# 步骤 1: 替换要更新的文件 (只动这些, 其他保留 base 配置)
cp ubuntu/build_v3s/dji_rc "$OUT/usr/local/bin/dji_rc"        # crsf-bridge 版
cp ubuntu/build_v3s/web_server "$OUT/usr/local/bin/web_server" # 含新 VERSION
cp ubuntu/scripts/S99tun_nat_hub "$OUT/etc/init.d/S99tun_nat_hub"
cp ubuntu/scripts/setup_v3s.sh "$OUT/usr/local/bin/setup_v3s.sh"

# 步骤 2: 校验关键配置没丢
grep -n "172\." "$OUT/usr/local/bin/setup_v3s.sh"   # 必须看到 172.20.10.3
head -1 "$OUT/etc/init.d/S99tun_nat_hub" | xxd       # 必须 #!/bin/sh\n (LF, 无 \r\n)

# 步骤 3: 打包 (XZ + 12B 验证尾)
mksquashfs "$OUT" /tmp/rootfs_v165.sq -comp xz -b 131072 -noappend
python3 tmp/_add_rootfs_tail.py /tmp/rootfs_v165.sq backup/rootfs_v165.squashfs

# 步骤 4: 读回校验 (必须做!)
unsquashfs -q -d /home/xlong/v165_check backup/rootfs_v165.squashfs
md5sum /home/xlong/v165_check/usr/local/bin/dji_rc       # 应 = 本地 build_v3s/dji_rc
grep -c "172\." /home/xlong/v165_check/usr/local/bin/setup_v3s.sh  # ≥1
```

### ⚠️ S99/脚本必须 LF 换行（busybox sh 不认 CRLF）

S99tun_nat_hub 等脚本**必须是 LF 换行**。CRLF 的 `#!/bin/sh\r\n` 会让 busybox sh 报 `not found`，整个服务链（usb_tund/web_server/dji_rc）都不启动 → 设备无 IP 连不上。

- 项目 `.gitattributes` 已强制 `*.sh text eol=lf`、`*.lua text eol=lf`
- 构建前确认：`head -1 ubuntu/scripts/S99tun_nat_hub | xxd` 结尾是 `0a` 不是 `0d 0a`
- 从 Windows 编辑过的文件尤其要检查（git 可能转 CRLF）

### 可复用脚本

- `tmp/_build_v165_v2.sh` — 完整构建流程 (base 提取 → 替换 → 打包 → 读回校验)
- `tmp/_add_rootfs_tail.py` — 加 12B 验证尾 (TUN_NAT_HUB + CRC32)

---

## 3. SPI 全量镜像

```bash
# 从已有 SPI 镜像中替换 rootfs 部分
python3 -c "
SPI_SIZE=16*1024*1024
with open('backup/spi_image.bin','rb') as f: old=f.read()
with open('backup/rootfs.squashfs','rb') as f: sq=f.read()
offset=old.find(b'hsqs')
img=bytearray(old[:offset])+sq
img.extend(bytearray([0xFF]*(SPI_SIZE-len(img))))
with open('backup/spi_image.bin','wb') as f: f.write(bytes(img))
print(f'Done, free: {(SPI_SIZE-(offset+len(sq)))//1024}KB')
"
```

---

## 4. 部署

### Web 升级（推荐）
1. 访问 `http://192.168.144.66:8080`
2. 固件升级区域 → 选 `backup/rootfs.squashfs` → 上传
3. 自动 flash_erase + dd 写入 + SPL 标记 → 重启生效

### FEL 全量刷写
```bash
# V3s 进 FEL 模式后
wsl -u root sunxi-fel spiflash-write 0 backup/spi_image.bin
```

---

## 5. 版本管理

**版本号定义:** `ubuntu/src/web_server.cpp` `#define VERSION`

**同步位置:**
- `ubuntu/scripts/S99tun_nat_hub` — 启动日志
- `docs/CHANGELOG.md` — 变更记录

---

## 6. 发布检查清单

- [ ] `VERSION` 宏已更新
- [ ] S99 启动日志版本同步
- [ ] 用 Buildroot 工具链编译（不是 Ubuntu 的 arm-linux-gnueabihf-g++）
- [ ] `strings web_server | grep VERSION` 确认版本号
- [ ] rootfs.squashfs 重新打包
- [ ] spi_image.bin 同步更新
- [ ] Web 面板 `http://192.168.144.66:8080/api/version` 验证
