# Channel Config Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current folded RC channel configuration card with a dark TUN_NAT_HUB styled channel-setting workbench modeled after the reference app's content structure.

**Architecture:** Keep the implementation inside the existing `MainActivity.kt` because the app currently defines RC page UI and API helpers there. Add small pure helper functions for map normalization and range sanitizing so behavior can be tested without Compose UI instrumentation. Preserve the existing V3s `/api/rc/output` JSON contract.

**Tech Stack:** Kotlin, Jetpack Compose Material3, existing Android Gradle project, Java/Kotlin unit-style tests, V3s HTTP API.

---

## File Structure

- Modify `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
  - Add pure helpers for channel maps, source labels, source config keys, range validation, and source grouping.
  - Replace `RemoteChannelConfig()` content with the dark workbench UI.
  - Add source picker dialog and per-channel row components near the existing RC page code.
- Modify `android/app/build.gradle.kts`
  - Bump app version to `versionCode = 56` and `versionName = "1.6.17"`.
- Create `android/app/src/test/java/com/tunnathub/app/ChannelConfigWorkbenchTest.java`
  - Test helper behavior by calling Kotlin top-level functions from Java.

## Task 1: Add Testable Channel Config Helpers

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
- Create: `android/app/src/test/java/com/tunnathub/app/ChannelConfigWorkbenchTest.java`

- [ ] **Step 1: Write failing helper tests**

Create `android/app/src/test/java/com/tunnathub/app/ChannelConfigWorkbenchTest.java`:

```java
package com.tunnathub.app;

import java.util.Arrays;
import java.util.List;

public final class ChannelConfigWorkbenchTest {
    public static void main(String[] args) {
        normalizesMapToSixteenChannels();
        clampsAndOrdersRangeValues();
        mapsSourceToStickRangeKeys();
        mapsSwitchSourceToOnOffKeys();
        labelsKnownSourcesForTheWorkbench();
    }

    private static void normalizesMapToSixteenChannels() {
        List<String> result = MainActivityKt.channelMapToListForTest("ch1,ch3,mode");
        assertEquals(16, result.size(), "normalized map size");
        assertEquals("ch1", result.get(0), "CH1 source");
        assertEquals("ch3", result.get(1), "CH2 source");
        assertEquals("mode", result.get(2), "CH3 source");
        assertEquals("none", result.get(15), "CH16 fallback");

        String joined = MainActivityKt.channelMapToStringForTest(result);
        assertEquals("ch1,ch3,mode,none,none,none,none,none,none,none,none,none,none,none,none,none", joined, "joined map");
    }

    private static void clampsAndOrdersRangeValues() {
        int[] ordered = MainActivityKt.sanitizeChannelRangeForTest(2300, 700);
        assertEquals(800, ordered[0], "range min clamp");
        assertEquals(2200, ordered[1], "range max clamp");

        int[] swapped = MainActivityKt.sanitizeChannelRangeForTest(1900, 1100);
        assertEquals(1100, swapped[0], "range swap min");
        assertEquals(1900, swapped[1], "range swap max");
    }

    private static void mapsSourceToStickRangeKeys() {
        String[] keys = MainActivityKt.sourceRangeKeysForTest("ch1");
        assertEquals("st1_min", keys[0], "stick min key");
        assertEquals("st1_max", keys[1], "stick max key");
        assertEquals("st1_mid", keys[2], "stick mid key");
        assertEquals("st1_rev", keys[3], "stick rev key");
    }

    private static void mapsSwitchSourceToOnOffKeys() {
        String[] keys = MainActivityKt.sourceRangeKeysForTest("rec");
        assertEquals("rec_off", keys[0], "switch off key");
        assertEquals("rec_on", keys[1], "switch on key");
        assertEquals("", keys[2], "switch mid key");
        assertEquals("", keys[3], "switch rev key");
    }

    private static void labelsKnownSourcesForTheWorkbench() {
        assertEquals("J1", MainActivityKt.sourceDisplayLabelForTest("ch1"), "J1 label");
        assertEquals("飞行模式", MainActivityKt.sourceDisplayLabelForTest("mode"), "mode label");
        assertEquals("无", MainActivityKt.sourceDisplayLabelForTest("none"), "none label");
        assertEquals("custom", MainActivityKt.sourceDisplayLabelForTest("custom"), "custom passthrough");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }

    private static void assertEquals(int expected, int actual, String name) {
        if (expected != actual) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: compilation fails because `MainActivityKt.channelMapToListForTest`, `channelMapToStringForTest`, `sanitizeChannelRangeForTest`, `sourceRangeKeysForTest`, and `sourceDisplayLabelForTest` do not exist.

- [ ] **Step 3: Add pure helper implementation**

In `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`, add these top-level helpers after `SRC_CFG_GROUPS`:

```kotlin
private const val CHANNEL_COUNT = 16

private data class SourceKeys(
    val minKey: String = "",
    val maxKey: String = "",
    val midKey: String = "",
    val revKey: String = ""
)

private fun channelMapToList(map: String): List<String> {
    val values = map.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    return List(CHANNEL_COUNT) { idx -> values.getOrNull(idx) ?: "none" }
}

private fun channelMapToString(values: List<String>): String =
    List(CHANNEL_COUNT) { idx -> values.getOrNull(idx)?.takeIf { it.isNotBlank() } ?: "none" }
        .joinToString(",")

private fun sanitizeChannelRange(min: Int, max: Int): Pair<Int, Int> {
    val a = min.coerceIn(800, 2200)
    val b = max.coerceIn(800, 2200)
    return if (a <= b) a to b else b to a
}

private fun sourceKeys(source: String): SourceKeys = when {
    source.matches(Regex("ch[1-6]")) -> {
        val n = source.removePrefix("ch")
        SourceKeys("st${n}_min", "st${n}_max", "st${n}_mid", "st${n}_rev")
    }
    source == "dial" -> SourceKeys("dial_min", "dial_max", "", "dial_rev")
    source == "mode" -> SourceKeys("mode_s", "mode_f", "mode_n", "")
    source == "shot" -> SourceKeys("shot_lo", "shot_hi", "shot_mid", "")
    source == "c12" -> SourceKeys("c12_0", "c12_3", "", "")
    source == "dir" -> SourceKeys("dir_0", "dir_5", "", "")
    source in setOf("rec", "focus", "fn", "pause", "c1", "c2", "five", "cam", "gimbal") ->
        SourceKeys("${source}_off", "${source}_on", "", "")
    else -> SourceKeys()
}

private fun sourceDisplayLabel(source: String): String = when (source) {
    "none" -> "无"
    "ch1" -> "J1"
    "ch2" -> "J2"
    "ch3" -> "J3"
    "ch4" -> "J4"
    "ch5" -> "J5"
    "ch6" -> "J6"
    "dial" -> "V1"
    "mode" -> "飞行模式"
    "rec" -> "录像"
    "focus" -> "对焦"
    "fn" -> "Fn"
    "pause" -> "暂停"
    "shot" -> "快门"
    "c12" -> "C1/C2"
    "dir" -> "方向键"
    else -> source
}

fun channelMapToListForTest(map: String): List<String> = channelMapToList(map)
fun channelMapToStringForTest(values: List<String>): String = channelMapToString(values)
fun sanitizeChannelRangeForTest(min: Int, max: Int): IntArray {
    val r = sanitizeChannelRange(min, max)
    return intArrayOf(r.first, r.second)
}
fun sourceRangeKeysForTest(source: String): Array<String> {
    val keys = sourceKeys(source)
    return arrayOf(keys.minKey, keys.maxKey, keys.midKey, keys.revKey)
}
fun sourceDisplayLabelForTest(source: String): String = sourceDisplayLabel(source)
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: new `ChannelConfigWorkbenchTest` passes along with existing unit tests.

- [ ] **Step 5: Commit helper work**

Run:

```powershell
git -c safe.directory=C:/my_project/TUN_NAT_HUB add android/app/src/main/java/com/tunnathub/app/MainActivity.kt android/app/src/test/java/com/tunnathub/app/ChannelConfigWorkbenchTest.java
git -c safe.directory=C:/my_project/TUN_NAT_HUB commit -m "test(android): 覆盖通道设置工作台配置辅助逻辑"
```

## Task 2: Replace Folded Form With Dark Workbench UI

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`

- [ ] **Step 1: Add workbench state helpers inside `RemoteChannelConfig()`**

Replace `mapExpanded` and `srcCfgExpanded` state with:

```kotlin
var selectedSourceChannel by remember { mutableStateOf<Int?>(null) }
var roMsg by remember { mutableStateOf("") }
var roReload by remember { mutableStateOf(0) }
var loaded by remember { mutableStateOf(false) }
```

In the successful config load block, after setting `roMap`, normalize it:

```kotlin
roMap = channelMapToString(channelMapToList(jsonString(res, "map") ?: ""))
```

- [ ] **Step 2: Add reusable dark workbench components**

Inside `RemoteChannelConfig()`, before the main `Surface`, add these local Composables:

```kotlin
@Composable
fun WorkbenchButton(label: String, active: Boolean = false, onClick: () -> Unit) {
    Surface(
        color = if (active) Color(0xFF0EA5E9) else Color(0xFF1E293B),
        shape = RoundedCornerShape(6.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, if (active) Color(0xFF38BDF8) else Color(0xFF334155)),
        onClick = onClick
    ) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.height(34.dp).padding(horizontal = 14.dp)) {
            Text(label, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = if (active) Color.Black else Color(0xFFE2E8F0))
        }
    }
}

@Composable
fun ChannelScale(value: Int) {
    val pct = ((value - 800).coerceIn(0, 1400) / 1400f)
    Box(modifier = Modifier.fillMaxWidth().height(30.dp)) {
        Box(modifier = Modifier.align(Alignment.Center).fillMaxWidth().height(4.dp).background(Color(0xFF334155), RoundedCornerShape(2.dp)))
        Box(modifier = Modifier.align(Alignment.CenterStart).fillMaxWidth(pct).height(4.dp).background(Color(0xFF0EA5E9), RoundedCornerShape(2.dp)))
        Text("$value", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.White,
            modifier = Modifier.align(Alignment.TopCenter).background(Color(0xFF0369A1), RoundedCornerShape(3.dp)).padding(horizontal = 5.dp, vertical = 1.dp))
    }
}

@Composable
fun RangeEditor(source: String, values: Map<String, Int>, onValue: (String, Int) -> Unit) {
    val keys = sourceKeys(source)
    if (keys.minKey.isEmpty() || keys.maxKey.isEmpty()) {
        Text("不可调", fontSize = 9.sp, color = Color(0xFF475569))
        return
    }
    val minVal = values[keys.minKey] ?: 1000
    val maxVal = values[keys.maxKey] ?: 2000
    var minText by remember(source, minVal) { mutableStateOf(minVal.toString()) }
    var maxText by remember(source, maxVal) { mutableStateOf(maxVal.toString()) }
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = minText,
            onValueChange = { txt ->
                minText = txt.filter { it.isDigit() }.take(4)
                minText.toIntOrNull()?.let { v -> onValue(keys.minKey, sanitizeChannelRange(v, maxVal).first) }
            },
            singleLine = true,
            textStyle = LocalTextStyle.current.copy(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
            modifier = Modifier.width(62.dp).height(46.dp)
        )
        Text(",", fontSize = 10.sp, color = Color(0xFF64748B))
        OutlinedTextField(
            value = maxText,
            onValueChange = { txt ->
                maxText = txt.filter { it.isDigit() }.take(4)
                maxText.toIntOrNull()?.let { v -> onValue(keys.maxKey, sanitizeChannelRange(minVal, v).second) }
            },
            singleLine = true,
            textStyle = LocalTextStyle.current.copy(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
            modifier = Modifier.width(62.dp).height(46.dp)
        )
    }
}
```

- [ ] **Step 3: Add source picker dialog**

Still inside `RemoteChannelConfig()`, add:

```kotlin
@Composable
fun SourcePickerDialog(channelIndex: Int, current: String, sources: List<String>, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    val groups = listOf(
        "摇杆&旋钮" to listOf("ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "dial"),
        "开关/按键" to listOf("rec", "focus", "fn", "pause", "c1", "c2", "five", "cam", "gimbal"),
        "功能键" to listOf("mode", "shot", "c12", "dir", "none")
    )
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF0F172A),
        title = { Text("CH${channelIndex + 1} 控件选择", color = Color(0xFFE2E8F0), fontSize = 16.sp, fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                groups.forEach { (name, items) ->
                    Text(name, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                    items.filter { it == "none" || sources.isEmpty() || sources.contains(it) }.chunked(4).forEach { rowItems ->
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            rowItems.forEach { src ->
                                WorkbenchButton(sourceDisplayLabel(src), active = src == current) { onPick(src) }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } }
    )
}
```

- [ ] **Step 4: Replace card body with A-style workbench**

Replace the old folded sections in the main `Surface` with:

```kotlin
val channelSources = channelMapToList(roMap)
Column(modifier = Modifier.padding(12.dp)) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column {
            Text("通道设置", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
            Text("CH1-CH16 输出源 / 范围 / 反向", fontSize = 9.sp, color = Color(0xFF64748B))
        }
        Text(if (loaded) "● 已连接" else "○ 未连接", fontSize = 9.sp, color = if (loaded) Color(0xFF22C55E) else Color(0xFFF59E0B))
    }
    Spacer(Modifier.height(10.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        WorkbenchButton("默认配置") {
            roPreset = "default"
            roMap = channelMapToString(List(CHANNEL_COUNT) { "ch${it + 1}" })
            srcCfg = SRC_CFG_GROUPS.flatMap { it.second }.associate { it.key to it.def }
            roMsg = "已恢复默认, 保存后生效"
        }
        WorkbenchButton("载入配置") { roMsg = "载入配置入口已预留" }
        WorkbenchButton("配置另存") { roMsg = "配置另存入口已预留" }
        WorkbenchButton("参数管理") { roMsg = "参数管理入口已预留" }
        Spacer(Modifier.weight(1f))
        WorkbenchButton("SBUS", roMode == "sbus") { roMode = "sbus" }
        WorkbenchButton("CRSF", roMode == "crsf") { roMode = "crsf" }
    }
    Spacer(Modifier.height(12.dp))
    Column(modifier = Modifier.fillMaxWidth().background(Color(0xFF111827), RoundedCornerShape(8.dp)).border(1.dp, Color(0xFF1E293B), RoundedCornerShape(8.dp)).padding(8.dp)) {
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("通道", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(42.dp))
            Text("控件", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(76.dp))
            Text("当前值", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.weight(1f))
            Text("反向", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(58.dp))
            Text("范围", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(144.dp))
        }
        channelSources.forEachIndexed { idx, source ->
            val keys = sourceKeys(source)
            val value = keys.midKey.takeIf { it.isNotEmpty() }?.let { srcCfg[it] } ?: 1500
            Row(modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).border(0.5.dp, Color(0xFF1E293B)).padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("CH${idx + 1}", fontSize = 11.sp, color = Color(0xFFE2E8F0), modifier = Modifier.width(42.dp))
                WorkbenchButton(sourceDisplayLabel(source)) { selectedSourceChannel = idx }
                Box(modifier = Modifier.width(8.dp))
                ChannelScale(value)
                Box(modifier = Modifier.width(8.dp))
                if (keys.revKey.isNotEmpty()) {
                    Checkbox(
                        checked = (srcCfg[keys.revKey] ?: 0) != 0,
                        onCheckedChange = { checked -> srcCfg = srcCfg + (keys.revKey to if (checked) 1 else 0) },
                        modifier = Modifier.width(50.dp)
                    )
                } else {
                    Text("-", fontSize = 11.sp, color = Color(0xFF475569), modifier = Modifier.width(50.dp))
                }
                RangeEditor(source, srcCfg) { k, v -> srcCfg = srcCfg + (k to v) }
            }
        }
    }
    Spacer(Modifier.height(10.dp))
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Button(onClick = {
            roMsg = ""
            val scJson = SRC_CFG_GROUPS.flatMap { it.second }.joinToString(",") { "\"${it.key}\":${srcCfg[it.key] ?: it.def}" }
            val scPart = if (srcCfgLoaded) ""","src_cfg":{$scJson}""" else ""
            val body = """{"mode":"$roMode","baud":"$roBaud","map_preset":"$roPreset","map":"${channelMapToString(channelSources)}","sbus_std":true$scPart}"""
            apiPost("/api/rc/output", body) { ok -> roMsg = if (ok) "已保存, V3s 将自动应用" else "保存失败, 请检查连接" }
        }, modifier = Modifier.height(34.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))) {
            Text("保存并应用", fontSize = 11.sp)
        }
        Button(onClick = { roReload++ }, modifier = Modifier.height(34.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))) {
            Text("刷新", fontSize = 11.sp)
        }
        if (roMsg.isNotEmpty()) Text(roMsg, fontSize = 9.sp, color = Color(0xFF94A3B8), modifier = Modifier.weight(1f))
    }
}
selectedSourceChannel?.let { idx ->
    SourcePickerDialog(idx, channelSources[idx], roSources, onPick = { src ->
        val next = channelSources.toMutableList()
        next[idx] = src
        roMap = channelMapToString(next)
        roPreset = "custom"
        selectedSourceChannel = null
    }, onDismiss = { selectedSourceChannel = null })
}
```

- [ ] **Step 5: Run Android unit tests**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: all tests pass.

- [ ] **Step 6: Commit workbench UI**

Run:

```powershell
git -c safe.directory=C:/my_project/TUN_NAT_HUB add android/app/src/main/java/com/tunnathub/app/MainActivity.kt
git -c safe.directory=C:/my_project/TUN_NAT_HUB commit -m "feat(android): 暗色通道设置工作台界面"
```

## Task 3: Version Bump and Build Verification

**Files:**
- Modify: `android/app/build.gradle.kts`

- [ ] **Step 1: Bump app version**

Change:

```kotlin
versionCode = 55
versionName = "1.6.16"
```

to:

```kotlin
versionCode = 56
versionName = "1.6.17"
```

- [ ] **Step 2: Build debug APK**

Run:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Expected: `BUILD SUCCESSFUL`, APK generated at `android/app/build/outputs/apk/debug/app-debug.apk`.

- [ ] **Step 3: Commit version bump**

Run:

```powershell
git -c safe.directory=C:/my_project/TUN_NAT_HUB add android/app/build.gradle.kts
git -c safe.directory=C:/my_project/TUN_NAT_HUB commit -m "chore(android): App 版本升至 1.6.17"
```

## Task 4: Final Review

**Files:**
- Review: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
- Review: `android/app/build.gradle.kts`
- Review: `android/app/src/test/java/com/tunnathub/app/ChannelConfigWorkbenchTest.java`

- [ ] **Step 1: Inspect git status**

Run:

```powershell
git -c safe.directory=C:/my_project/TUN_NAT_HUB status --short --branch
```

Expected: only pre-existing unrelated dirty files remain.

- [ ] **Step 2: Inspect final commits**

Run:

```powershell
git -c safe.directory=C:/my_project/TUN_NAT_HUB log --oneline -n 5
```

Expected: commits include helper tests, workbench UI, and version bump.

- [ ] **Step 3: Summarize verification**

Report:

```text
App 通道配置已改为暗色工作台。
验证:
- testDebugUnitTest: PASS
- assembleDebug: PASS
版本:
- App 1.6.17 / versionCode 56
```
