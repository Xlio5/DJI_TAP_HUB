# Android App 编译环境需求（GStreamer SDK 说明）

> 目的：说明编译本工程 Android App 需要哪些**额外预装**的依赖，避免"另一台电脑 clone 后编译失败"的歧义。
> 更新时间：2026-08-14

---

## 一、关键结论

**GStreamer Android SDK 是本工程的硬依赖，且它不随 git 提交（近 2GB），每台编译机必须自行放置。**

如果编译报错：
```
GStreamer SDK not found at <project>/android/app/src/main/gstreamer_libs/arm64.
Download and extract first.
```
不是工程缺文件，而是**该编译机还没放 GStreamer SDK**。

---

## 二、GStreamer SDK 详情

| 项 | 值 |
|---|---|
| 软件 | GStreamer Android SDK（静态库 + 头文件） |
| **版本** | **1.28.4**（`gstversion.h` 确认，`GST_VERSION 1.28.4.0`） |
| 目标 ABI | **arm64-v8a**（`build.gradle.kts` 只编这个） |
| 在工程中的路径 | `android/app/src/main/gstreamer_libs/arm64/` |
| 大小 | **~1.99 GB** |
| git 状态 | **被 `.gitignore` 忽略**（`android/.gitignore:2` → `app/src/main/gstreamer_libs/`），不随 git 提交 |

### 必需目录结构
```
android/app/src/main/gstreamer_libs/arm64/
├── include/          # GStreamer + glib + libxml2 + 各插件头
└── lib/
    ├── *.a           # GStreamer 核心 + 插件静态库
    └── gstreamer-1.0/  # 插件 .a (libgstrtsp/libgstplayback/libgstandroidmedia 等)
```

### 哪些插件被用（CMakeLists.txt 硬链接）
RTSP、RTP、RTPmanager、Playback、Coreelements、App、Videoconvertscale、Videoparsersbad、Androidmedia、Typefindfunctions、TCP、UDP、SDP、OpenH264、OpenGL

---

## 三、为什么必须有它

1. **NDK native 库**，不是 gradle 依赖：App 用 `gstqgc_player.c`（QGC GStreamer 播放引擎），经 NDK 编译成 `libgstqgcplayer.so`
2. [CMakeLists.txt:5-8](android/app/src/main/cpp/CMakeLists.txt#L5-L8) 硬检查路径，不存在直接 `FATAL_ERROR`
3. SDK 近 2GB，进 git 会严重拖慢 clone/同步 → `.gitignore` 排除

---

## 四、编译机如何准备

### 方式一：从本机拷贝（最快）
把本机 `android/app/src/main/gstreamer_libs/` 整个目录（含 arm64/）拷到另一台电脑的**完全相同路径**：
```
android/app/src/main/gstreamer_libs/   (~2GB)
```

### 方式二：官方下载
从 GStreamer Android SDK 官方渠道下载 **arm64** 版（**版本 1.28.4**，或相近的 1.28.x），解压后放到同样路径：
```
android/app/src/main/gstreamer_libs/arm64/
```

> ⚠️ 版本需匹配 CMakeLists.txt 引用的库名（`libgstrtsp.a`、`libgstandroidmedia.a` 等）。若用不同版本，库名可能变化，需同步改 CMakeLists.txt。

---

## 五、其他编译环境需求（完整清单）

| 组件 | 要求 | 说明 |
|---|---|---|
| JDK | 17 | `build.gradle.kts` sourceCompatibility = 17 |
| Android SDK | compileSdk 34 | `compileSdk = 34` |
| NDK | 含 CMake 3.22.1 | `build.gradle.kts` 指定 cmake version 3.22.1 |
| Gradle | wrapper 自动 | 用 `./gradlew`，无需手动装 |
| GStreamer SDK | **1.28.4 arm64** | **本文档核心**，预装到指定路径 |

---

## 六、验证是否就绪

编译前检查 SDK 是否存在：
```powershell
Test-Path "android/app/src/main/gstreamer_libs/arm64/lib/libgstreamer-1.0.a"
# True = 就绪；False = 编译会报 GStreamer SDK not found
```

---

## 七、文档归属

- 本文件：`docs/ANDROID_BUILD_REQUIREMENTS.md`
- 关联：`docs/BUILD.md`（V3s 固件构建）、`android/app/src/main/cpp/CMakeLists.txt`（GStreamer 链接）
