---
name: ubuntu-dev
description: Ubuntu/Debian 系统开发 — C/C++ 项目、Python 服务、systemd 配置、网络编程
---

# Ubuntu/Debian 系统开发技能

用户想在 Ubuntu/Debian（含 Armbian、树莓派、Radxa 等 ARM 板）上做开发。你必须自主完成从项目创建到部署上线的全流程。

## 环境确认

```bash
uname -a                          # 看架构 (x86_64 / aarch64)
lsb_release -a                    # 看发行版
gcc --version                     # C 编译器
python3 --version                 # Python
cmake --version                   # CMake
dpkg -l | grep libsystemd-dev     # systemd 开发库
```

## 项目类型

根据用户需求选择：

### A. C/C++ 项目（推荐用于高性能 / 网络服务）

```
my-ubuntu-service/
├── CMakeLists.txt
├── src/
│   ├── main.cpp
│   ├── tcp_server.cpp
│   └── uart_bridge.cpp
├── include/
│   └── *.h
├── config/
│   └── config.yaml
├── scripts/
│   └── install.sh
└── debian/              # 打包用
    ├── control
    └── rules
```

CMakeLists.txt 模板：
```cmake
cmake_minimum_required(VERSION 3.16)
project(my_service VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Boost REQUIRED COMPONENTS system)
find_package(Threads REQUIRED)

add_executable(my_service
    src/main.cpp
    src/tcp_server.cpp
    src/uart_bridge.cpp
)

target_link_libraries(my_service
    Boost::system
    Threads::Threads
    pthread
)

install(TARGETS my_service DESTINATION /usr/local/bin)
```

### B. Python 项目

```
my-python-service/
├── pyproject.toml  (或 setup.py)
├── src/my_service/
│   ├── __init__.py
│   ├── main.py
│   └── server.py
├── tests/
│   └── test_server.py
└── systemd/
    └── my_service.service
```

## 子任务

### 1. 网络编程（TCP/UDP/WebSocket）

```cpp
// TCP Server 骨架 (Boost.Asio)
#include <boost/asio.hpp>
using boost::asio::ip::tcp;

class TcpServer {
    boost::asio::io_context io_;
    tcp::acceptor acceptor_;
public:
    TcpServer(int port) : acceptor_(io_, tcp::endpoint(tcp::v4(), port)) {}
    void run() { /* async_accept + read/write */ }
};
```

```python
# Python 版本 (asyncio)
import asyncio

async def handle_client(reader, writer):
    data = await reader.read(1024)
    writer.write(data)
    await writer.drain()

async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', 8888)
    await server.serve_forever()
```

### 2. 串口通信（连接嵌入式设备）

```cpp
// Linux termios 串口
#include <fcntl.h>
#include <termios.h>

int uart_open(const char *dev, int baud) {
    int fd = open(dev, O_RDWR | O_NOCTTY);
    struct termios tty;
    tcgetattr(fd, &tty);
    cfsetospeed(&tty, B115200);
    tty.c_cflag |= CLOCAL | CREAD;
    tty.c_cflag &= ~CRTSCTS;
    tcsetattr(fd, TCSANOW, &tty);
    return fd;
}
```

### 3. systemd 服务

```ini
# /etc/systemd/system/my_service.service
[Unit]
Description=My Ubuntu Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/my_service
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

安装：
```bash
sudo cp my_service.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable my_service
sudo systemctl start my_service
sudo systemctl status my_service
```

### 4. Debian 打包（可选）

```bash
# debian/control
Source: my-service
Section: utils
Package: my-service
Architecture: arm64  # 或 amd64
Depends: libboost-system1.74.0

# 构建 .deb
dpkg-buildpackage -us -uc -b
```

## 跨架构编译（x64 → ARM64）

```bash
# 安装交叉编译链
sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu

# CMake 交叉编译
cmake -DCMAKE_TOOLCHAIN_FILE=../arm64.toolchain.cmake ..
make -j$(nproc)

# arm64.toolchain.cmake:
# set(CMAKE_SYSTEM_NAME Linux)
# set(CMAKE_SYSTEM_PROCESSOR aarch64)
# set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
# set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
```

## 部署到 Radxa 5C

```bash
# SSH 推文件
scp my_service xlong@192.168.88.66:/tmp/
ssh xlong@192.168.88.66 "sudo mv /tmp/my_service /usr/local/bin/ && sudo systemctl restart my_service"

# 远程看日志
ssh xlong@192.168.88.66 "journalctl -u my_service -f"
```

## 注意

- 默认用 C++17 + CMake，Python 用 asyncio
- ARM64 交叉编译时注意字节序（全是 little-endian，一致的）
- systemd service 必须写 Restart=always
- 网络服务绑 0.0.0.0，不要只绑 localhost
