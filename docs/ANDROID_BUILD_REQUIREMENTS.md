# Android App 编译环境需求（GStreamer 说明）

> 目的：说明编译本工程 Android App 需要哪些依赖，避免"另一台电脑 clone 后编译失败"的歧义。
> 更新时间：2026-08-14

---

## 一、关键结论

**GStreamer 最小编译集已入库（`gstreamer_libs_min/`），clone 后无需任何额外预装即可直接编译。**

2026-08-14 起，GStreamer 依赖从"预装近 2GB SDK"改为"最小编译集随 git 提交"：
- 新增 `android/app/src/main/gstreamer_libs_min/arm64/`（~178MB）：仅 CMake 实际链接的 51 个 `.a` + 头文件
- `CMakeLists.txt` 的 `GSTREAMER_ROOT` 指向 `gstreamer_libs_min`
- 效果：另一台电脑 clone 后直接 `./gradlew assembleDebug` 即可编译，无需准备 GStreamer SDK

---

## 二、GStreamer 依赖详情

| 项 | 值 |
|---|---|
| 软件 | GStreamer Android SDK（静态库 + 头文件） |
| **版本** | **1.28.4**（`gstversion.h` 确认，`GST_VERSION 1.28.4.0`） |
| 目标 ABI | **arm64-v8a**（`build.gradle.kts` 只编这个） |
| 工程路径 | `android/app/src/main/gstreamer_libs_min/arm64/` |
| 大小 | **~178 MB** |
| git 状态 | **随 git 提交**（`gstreamer_libs_min/` 入库；全量 2GB 的 `gstreamer_libs/` 仍被 `.gitignore` 排除） |

### 必需目录结构
```
android/app/src/main/gstreamer_libs_min/arm64/
├── include/          # GStreamer + glib + libxml2 + 各插件头
└── lib/
    ├── *.a           # GStreamer 核心 + 插件静态库
    └── gstreamer-1.0/  # 插件 .a (libgstrtsp/libgstplayback/libgstandroidmedia 等)
```

### 哪些插件被用（CMakeLists.txt 硬链接）
RTSP、RTP、RTPmanager、Playback、Coreelements、App、Videoconvertscale、Videoparsersbad、Androidmedia、Typefindfunctions、TCP、UDP、SDP、OpenH264、OpenGL

---

## 三、min 集怎么来的（背景）

- **为什么需要**：App 用 `gstqgc_player.c`（QGC GStreamer 播放引擎），经 NDK 编译成 `libgstqgcplayer.so`；全量 GStreamer SDK 近 2GB，进 git 会严重拖慢 clone/同步
- **如何提取**：从全量 `gstreamer_libs/`（2GB）用 `build.ninja` 精确识别实际被链接的库，提取 51 个 `.a` + 头文件；编译验证 `libgstqgcplayer.so` 通过，`.a` 内容 md5 与源一致
- **何时需要全量**：若未来新增插件链接（CMakeLists 引用新 `.a`），需从全量 SDK 提取补入 min 集

---

## 四、编译环境需求（完整清单）

| 组件 | 要求 | 说明 |
|---|---|---|
| JDK | 17 | `build.gradle.kts` sourceCompatibility = 17 |
| Android SDK | compileSdk 34 | `compileSdk = 34` |
| NDK | 含 CMake 3.22.1 | `build.gradle.kts` 指定 cmake version 3.22.1 |
| Gradle | wrapper 自动 | 用 `./gradlew`，无需手动装 |
| GStreamer | **已入库（gstreamer_libs_min）** | **无需额外准备** |

---

## 五、验证是否就绪

编译前检查 min 集是否存在：
```powershell
Test-Path "android/app/src/main/gstreamer_libs_min/arm64/lib/libgstreamer-1.0.a"
# True = 就绪；False = 需先 pull 到含 gstreamer_libs_min 的提交
```

---

## 六、文档归属

- 本文件：`docs/ANDROID_BUILD_REQUIREMENTS.md`
- 关联：`docs/BUILD.md`（V3s 固件构建）、`android/app/src/main/cpp/CMakeLists.txt`（GStreamer 链接）
