---
name: android-dev
description: Android APK 全流程开发 — 项目初始化、Kotlin 编码、Gradle 构建、APK 签名部署
---

# Android APK 开发技能

用户想要开发 Android APK。你必须自主完成从项目初始化到 APK 部署的全流程。

## 前置检查

首次使用时，检查环境：
```bash
# 检查 Java
java -version

# 检查 Android SDK（如果没装，引导安装）
echo $ANDROID_HOME
ls $ANDROID_HOME/platforms/

# 检查 Gradle
gradle --version

# 检查 ADB + 设备
adb devices
```

如果没有 Android SDK：
```bash
# Windows: 安装 cmdline-tools
# 下载 https://developer.android.com/studio#command-line-tools-only
# 解压到 ~/Android/cmdline-tools/latest/
# 设置环境变量 ANDROID_HOME=~/Android
# 安装 SDK 组件：
sdkmanager "platforms;android-34" "build-tools;34.0.0" "platform-tools"
```

## 项目目录结构

```
my-android-app/
├── app/
│   ├── src/main/
│   │   ├── java/com/example/app/
│   │   │   └── MainActivity.kt
│   │   ├── res/
│   │   │   ├── layout/activity_main.xml
│   │   │   └── values/strings.xml
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
└── gradle/wrapper/gradle-wrapper.properties
```

## 子任务

### A. 创建项目

1. 确保 `ANDROID_HOME` 已设置
2. 用 Gradle Wrapper 初始化项目（不依赖 Android Studio）
3. 写入 `build.gradle.kts`（顶层 + app 层）

关键 build.gradle.kts（app层）：
```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android") version "1.9.0"
}

android {
    namespace = "com.example.app"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.example.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
    buildFeatures { viewBinding = true }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
}
```

### B. 写 Kotlin 代码

- 遵循 Android 最佳实践
- 使用 ViewBinding 或 Jetpack Compose（根据用户偏好）
- 权限在 AndroidManifest.xml 中声明
- 网络操作用 OkHttp / Retrofit
- 串口通信用 android-serialport-api

### C. 构建 APK

```bash
# Debug APK
./gradlew assembleDebug

# Release APK（需先生成 keystore）
keytool -genkey -v -keystore app.keystore -alias app -keyalg RSA -keysize 2048 -validity 10000
./gradlew assembleRelease
```

### D. 部署

```bash
# 通过 ADB
adb install -r app/build/outputs/apk/debug/app-debug.apk

# 启动
adb shell am start -n com.example.app/.MainActivity

# 看日志
adb logcat | grep -E "AndroidRuntime|com.example.app"
```

## 网络 ADB（无线调试）

```bash
# 如果设备在 WiFi 上：
adb tcpip 5555
adb connect 设备IP:5555

# 验证
adb devices
```

## 注意

- 所有生成的文件使用中文注释
- 默认 targetSdk 34, minSdk 26
- 第一步永远是检查 `adb devices` 确认有设备连着
- 如果用户没指定 App 功能，先问清楚需求再开始写代码
