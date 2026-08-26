# ADB Getevent RC Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new RC acquisition path where high-frequency joystick values come from DJI RC Android input events and low-frequency joystick/key state comes from UDP port 40007, then fuse them into the existing unified RC state used by channel mapping, lock, rcmsg display, and V3s output.

**Architecture:** Keep V3s `rc_state_t` and channel mapping as the single downstream contract. Add Android-side acquisition modules for getevent and 40007, a pure fusion engine that prefers fresh high-frequency stick axes while preserving keys from 40007, and an explicit App-to-V3s RC uplink so V3s can output SBUS/CRSF from the fused state. Add a feasibility gate first because `adb shell getevent` proves the shell user can read input devices, but the APK process may not have the same permission.

**Tech Stack:** Kotlin, Android coroutines, UDP sockets, existing `TunNatVpnService` protected socket helpers, C/C++ V3s `dji_rc`, existing `rc_state_t` / `rc_merge` / `rc_map` / `RcMsg`.

---

## File Structure

- Create `android/app/src/main/java/com/tunnathub/app/rc/RcInputSample.kt`
  - Shared Android data model for stick axes, keys, timestamps, and source freshness.
- Create `android/app/src/main/java/com/tunnathub/app/rc/GetEventRcReader.kt`
  - Starts and parses `getevent -lt` output when available; maps Linux input events to six stick axes.
- Create `android/app/src/main/java/com/tunnathub/app/rc/Port40007RcReader.kt`
  - Receives low-frequency RC packets from UDP `40007`; extracts stick and key fields.
- Create `android/app/src/main/java/com/tunnathub/app/rc/RcFusionEngine.kt`
  - Pure fusion logic: getevent axes win while fresh; 40007 supplies keys and fallback axes.
- Create `android/app/src/main/java/com/tunnathub/app/rc/RcUplink.kt`
  - Sends fused RC state from App to V3s over a new UDP uplink port.
- Modify `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
  - Replace direct `RcMsg` UI updates with fused local state where enabled; keep old V3s rcmsg path visible as diagnostic.
- Modify `android/app/src/main/java/com/tunnathub/app/service/TunNatVpnService.kt`
  - Reuse protected socket helpers for the App-to-V3s uplink and 40007 listener if the packet path goes through TUN.
- Create `android/app/src/test/java/com/tunnathub/app/rc/RcFusionEngineTest.java`
  - Covers freshness, key preservation, stale fallback, and no-double-toggle assumptions.
- Create `android/app/src/test/java/com/tunnathub/app/rc/GetEventRcReaderTest.java`
  - Covers parsing real `getevent` lines into axes.
- Create `android/app/src/test/java/com/tunnathub/app/rc/Port40007RcReaderTest.java`
  - Covers the confirmed 40007 packet format after Task 1 captures it.
- Modify `ubuntu/src/rc_decode.h`
  - Add `RC_APP_FUSED` source type.
- Modify `ubuntu/src/dji_rc.cpp`
  - Add App RC uplink UDP receiver, merge it into the existing unified RC state, and expose diagnostics in `/tmp/dji_rc_state.json`.
- Modify `ubuntu/src/web_server.cpp`
  - Surface `app_rc_good`, `app_rc_age_ms`, `getevent_hz`, `p40007_hz`, and active source in `/api/rc`.
- Modify `.claude/prds/tun-nat-hub-core.prd.md`
  - Record the product change: high-frequency stick source moves to Android input events, 40007 remains low-frequency fallback/key source.

## Task 1: Capture Real Input Contracts

**Files:**
- Create: `tmp/rc_getevent_capture_20260826.txt`
- Create: `tmp/rc_40007_capture_20260826.bin`
- Create: `docs/rc_input_contract_20260826.md`

- [ ] **Step 1: Capture getevent device list**

Run:

```powershell
adb connect 192.168.5.249:5555
adb -s 192.168.5.249:5555 shell getevent -lp > tmp/rc_getevent_capture_20260826.txt
```

Expected: `tmp/rc_getevent_capture_20260826.txt` contains at least one input device with absolute axes such as `ABS_X`, `ABS_Y`, `ABS_Z`, `ABS_RZ`, `ABS_RX`, or `ABS_RY`.

- [ ] **Step 2: Capture live getevent samples**

Run:

```powershell
adb -s 192.168.5.249:5555 shell "timeout 10 getevent -lt" >> tmp/rc_getevent_capture_20260826.txt
```

Expected: moving each stick produces repeated `EV_ABS` lines. Pressing keys may produce `EV_KEY`, but keys are not required from this source.

- [ ] **Step 3: Capture UDP 40007 samples**

Run:

```powershell
adb -s 192.168.5.249:5555 shell "timeout 10 toybox nc -lu -p 40007" > tmp/rc_40007_capture_20260826.bin
```

If `toybox nc` does not receive on device, run a small temporary APK-side socket capture during implementation instead. Expected: moving sticks and pressing keys changes bytes at stable offsets.

- [ ] **Step 4: Write the contract note**

Create `docs/rc_input_contract_20260826.md`:

```markdown
# RC Input Contract 2026-08-26

## getevent 高频摇杆

- 设备路径:
- 轴映射:
  - CH1:
  - CH2:
  - CH3:
  - CH4:
  - CH5:
  - CH6:
- 原始范围:
  - min:
  - mid:
  - max:
- 实测频率:
- APK 进程权限结论:
  - 能直接执行 `getevent`:
  - 不能直接执行时的降级方案:

## UDP 40007 低频摇杆和按键

- 本机监听地址:
- 包长度:
- 字节序:
- 通道字段:
- 按键字段:
- 实测频率:
- 丢包/空闲行为:

## 融合规则

1. 摇杆轴优先使用 getevent，fresh 窗口 80ms。
2. getevent 轴超过 80ms 未更新时，回落到 40007 轴。
3. 按键、模式、拨轮优先使用 40007。
4. 自锁 latch 仍只在 V3s 的统一 RC 状态中推进一次。
```

- [ ] **Step 5: Commit capture contract**

Run:

```powershell
git add docs/rc_input_contract_20260826.md
git commit -m "docs(rc): 记录 getevent 与 40007 输入契约"
```

Do not commit `tmp/` capture files unless the user explicitly asks to archive raw samples.

## Task 2: Add Pure Android Fusion Model

**Files:**
- Create: `android/app/src/main/java/com/tunnathub/app/rc/RcInputSample.kt`
- Create: `android/app/src/main/java/com/tunnathub/app/rc/RcFusionEngine.kt`
- Create: `android/app/src/test/java/com/tunnathub/app/rc/RcFusionEngineTest.java`

- [ ] **Step 1: Write failing fusion tests**

Create `android/app/src/test/java/com/tunnathub/app/rc/RcFusionEngineTest.java`:

```java
package com.tunnathub.app.rc;

import java.util.Arrays;

public final class RcFusionEngineTest {
    public static void main(String[] args) {
        freshGeteventAxesOverride40007Axes();
        staleGeteventFallsBackTo40007Axes();
        keysAlwaysComeFrom40007();
    }

    private static void freshGeteventAxesOverride40007Axes() {
        RcInputSample ge = RcInputSample.axes("getevent", Arrays.asList(10, 20, 30, 40, 50, 60), 1_000L);
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(1, 2, 3, 4, 5, 6), 1, 0, 1, 0, 1, 0, "N", 990L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_020L);
        assertEquals(10, out.getAxes().get(0), "CH1 from getevent");
        assertEquals(60, out.getAxes().get(5), "CH6 from getevent");
        assertEquals(1, out.getStop(), "STOP from 40007");
        assertEquals("N", out.getMode(), "mode from 40007");
    }

    private static void staleGeteventFallsBackTo40007Axes() {
        RcInputSample ge = RcInputSample.axes("getevent", Arrays.asList(10, 20, 30, 40, 50, 60), 900L);
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(1, 2, 3, 4, 5, 6), 0, 1, 0, 1, 0, 1, "S", 990L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_100L);
        assertEquals(1, out.getAxes().get(0), "CH1 fallback to 40007");
        assertEquals(6, out.getAxes().get(5), "CH6 fallback to 40007");
        assertEquals(1, out.getRec(), "REC from 40007");
    }

    private static void keysAlwaysComeFrom40007() {
        RcInputSample ge = RcInputSample.axes("getevent", Arrays.asList(100, 100, 100, 100, 100, 100), 1_000L);
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(0, 0, 0, 0, 0, 0), 1, 1, 1, 1, 1, 1, "F", 1_000L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_000L);
        assertEquals(1, out.getStop(), "STOP preserved");
        assertEquals(1, out.getFocus(), "FOCUS preserved");
        assertEquals(1, out.getShot(), "SHOT preserved");
        assertEquals(1, out.getRec(), "REC preserved");
        assertEquals(1, out.getC1(), "C1 preserved");
        assertEquals(1, out.getC2(), "C2 preserved");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
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

Expected: compilation fails because `RcInputSample` and `RcFusionEngine` do not exist.

- [ ] **Step 3: Add `RcInputSample`**

Create `android/app/src/main/java/com/tunnathub/app/rc/RcInputSample.kt`:

```kotlin
package com.tunnathub.app.rc

data class RcInputSample(
    val source: String,
    val axes: List<Int>,
    val stop: Int,
    val focus: Int,
    val shot: Int,
    val rec: Int,
    val c1: Int,
    val c2: Int,
    val mode: String,
    val timestampMs: Long
) {
    companion object {
        @JvmStatic
        fun axes(source: String, axes: List<Int>, timestampMs: Long): RcInputSample =
            RcInputSample(source, axes.padAxes(), 0, 0, 0, 0, 0, 0, "?", timestampMs)

        @JvmStatic
        fun full(
            source: String,
            axes: List<Int>,
            stop: Int,
            focus: Int,
            shot: Int,
            rec: Int,
            c1: Int,
            c2: Int,
            mode: String,
            timestampMs: Long
        ): RcInputSample =
            RcInputSample(source, axes.padAxes(), stop, focus, shot, rec, c1, c2, mode, timestampMs)
    }
}

private fun List<Int>.padAxes(): List<Int> =
    List(6) { idx -> getOrNull(idx) ?: 0 }
```

- [ ] **Step 4: Add `RcFusionEngine`**

Create `android/app/src/main/java/com/tunnathub/app/rc/RcFusionEngine.kt`:

```kotlin
package com.tunnathub.app.rc

object RcFusionEngine {
    private const val GETEVENT_FRESH_MS = 80L
    private const val PORT40007_FRESH_MS = 500L

    @JvmStatic
    fun fuse(getevent: RcInputSample?, port40007: RcInputSample?, nowMs: Long): RcInputSample {
        val geFresh = getevent != null && nowMs - getevent.timestampMs <= GETEVENT_FRESH_MS
        val p4Fresh = port40007 != null && nowMs - port40007.timestampMs <= PORT40007_FRESH_MS
        val axes = when {
            geFresh -> getevent!!.axes
            p4Fresh -> port40007!!.axes
            else -> List(6) { 0 }
        }
        val keys = if (p4Fresh) port40007!! else null
        return RcInputSample.full(
            source = when {
                geFresh && p4Fresh -> "getevent+40007"
                geFresh -> "getevent"
                p4Fresh -> "40007"
                else -> "none"
            },
            axes = axes,
            stop = keys?.stop ?: 0,
            focus = keys?.focus ?: 0,
            shot = keys?.shot ?: 0,
            rec = keys?.rec ?: 0,
            c1 = keys?.c1 ?: 0,
            c2 = keys?.c2 ?: 0,
            mode = keys?.mode ?: "?",
            timestampMs = nowMs
        )
    }
}
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: `RcFusionEngineTest` passes.

- [ ] **Step 6: Commit fusion model**

Run:

```powershell
git add android/app/src/main/java/com/tunnathub/app/rc/RcInputSample.kt android/app/src/main/java/com/tunnathub/app/rc/RcFusionEngine.kt android/app/src/test/java/com/tunnathub/app/rc/RcFusionEngineTest.java
git commit -m "feat(android): 添加 RC 输入融合模型"
```

## Task 3: Implement Getevent Reader

**Files:**
- Create: `android/app/src/main/java/com/tunnathub/app/rc/GetEventRcReader.kt`
- Create: `android/app/src/test/java/com/tunnathub/app/rc/GetEventRcReaderTest.java`

- [ ] **Step 1: Write parser tests from captured lines**

Create `android/app/src/test/java/com/tunnathub/app/rc/GetEventRcReaderTest.java` using real axis names from `docs/rc_input_contract_20260826.md`:

```java
package com.tunnathub.app.rc;

public final class GetEventRcReaderTest {
    public static void main(String[] args) {
        parsesAbsLine();
        ignoresSynLine();
    }

    private static void parsesAbsLine() {
        GetEventRcReader.AxisEvent event = GetEventRcReader.parseLine("[  123.456789] /dev/input/event4: EV_ABS ABS_X 00000400");
        assertEquals("ABS_X", event.getCode(), "axis code");
        assertEquals(1024, event.getValue(), "axis value");
    }

    private static void ignoresSynLine() {
        GetEventRcReader.AxisEvent event = GetEventRcReader.parseLine("[  123.456790] /dev/input/event4: EV_SYN SYN_REPORT 00000000");
        if (event != null) throw new AssertionError("SYN line should be ignored");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
```

- [ ] **Step 2: Implement parser and process runner**

Create `android/app/src/main/java/com/tunnathub/app/rc/GetEventRcReader.kt`:

```kotlin
package com.tunnathub.app.rc

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

class GetEventRcReader(
    private val axisMap: Map<String, Int>,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    data class AxisEvent(val code: String, val value: Int)

    suspend fun run() = withContext(Dispatchers.IO) {
        val axes = MutableList(6) { 0 }
        val process = ProcessBuilder("getevent", "-lt")
            .redirectErrorStream(true)
            .start()
        process.inputStream.bufferedReader().useLines { lines ->
            val iterator = lines.iterator()
            while (isActive && iterator.hasNext()) {
                val event = parseLine(iterator.next()) ?: continue
                val idx = axisMap[event.code] ?: continue
                axes[idx] = normalize(event.value)
                onSample(RcInputSample.axes("getevent", axes.toList(), nowMs()))
            }
        }
    }

    companion object {
        @JvmStatic
        fun parseLine(line: String): AxisEvent? {
            if (!line.contains(" EV_ABS ")) return null
            val parts = line.trim().split(Regex("\\s+"))
            val codeIndex = parts.indexOf("EV_ABS") + 1
            if (codeIndex <= 0 || codeIndex + 1 >= parts.size) return null
            val value = parts[codeIndex + 1].toIntOrNull(16) ?: return null
            return AxisEvent(parts[codeIndex], value)
        }

        fun normalize(raw: Int): Int = (raw - 1024).coerceIn(-1024, 1024)
    }
}
```

- [ ] **Step 3: Run Android tests**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: parser tests pass.

- [ ] **Step 4: Commit getevent reader**

Run:

```powershell
git add android/app/src/main/java/com/tunnathub/app/rc/GetEventRcReader.kt android/app/src/test/java/com/tunnathub/app/rc/GetEventRcReaderTest.java
git commit -m "feat(android): 解析 getevent 高频摇杆输入"
```

## Task 4: Implement 40007 Reader

**Files:**
- Create: `android/app/src/main/java/com/tunnathub/app/rc/Port40007RcReader.kt`
- Create: `android/app/src/test/java/com/tunnathub/app/rc/Port40007RcReaderTest.java`

- [ ] **Step 1: Define packet parser from captured contract**

Create `android/app/src/main/java/com/tunnathub/app/rc/Port40007RcReader.kt` with offsets from `docs/rc_input_contract_20260826.md`. The parser must return `null` for packets with wrong length or invalid header:

```kotlin
package com.tunnathub.app.rc

import java.net.DatagramPacket
import java.net.DatagramSocket

class Port40007RcReader(
    private val socketFactory: () -> DatagramSocket,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    fun runBlocking() {
        val socket = socketFactory()
        val buf = ByteArray(256)
        val pkt = DatagramPacket(buf, buf.size)
        while (!Thread.currentThread().isInterrupted) {
            socket.receive(pkt)
            parsePacket(pkt.data.copyOf(pkt.length), nowMs())?.let(onSample)
        }
    }

    companion object {
        const val PORT = 40007

        @JvmStatic
        fun parsePacket(packet: ByteArray, nowMs: Long): RcInputSample? {
            if (packet.size < 16) return null
            val axes = List(6) { idx ->
                val off = 2 + idx * 2
                val raw = ((packet[off].toInt() and 0xFF) or ((packet[off + 1].toInt() and 0xFF) shl 8))
                (raw - 1024).coerceIn(-1024, 1024)
            }
            val buttons = packet[14].toInt() and 0xFF
            val modeBits = packet[15].toInt() and 0x03
            val mode = when (modeBits) {
                0 -> "S"
                1 -> "N"
                2 -> "F"
                else -> "?"
            }
            return RcInputSample.full(
                "40007",
                axes,
                stop = (buttons shr 0) and 1,
                focus = (buttons shr 1) and 1,
                shot = (buttons shr 2) and 1,
                rec = (buttons shr 3) and 1,
                c1 = (buttons shr 4) and 1,
                c2 = (buttons shr 5) and 1,
                mode = mode,
                timestampMs = nowMs
            )
        }
    }
}
```

- [ ] **Step 2: Write parser tests using captured packets**

Create `android/app/src/test/java/com/tunnathub/app/rc/Port40007RcReaderTest.java` and replace the byte array with one real captured packet from Task 1:

```java
package com.tunnathub.app.rc;

public final class Port40007RcReaderTest {
    public static void main(String[] args) {
        parsesCapturedPacket();
        rejectsShortPacket();
    }

    private static void parsesCapturedPacket() {
        byte[] packet = new byte[] {
            0x00, 0x00,
            0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04,
            0x09, 0x01
        };
        RcInputSample sample = Port40007RcReader.parsePacket(packet, 1_000L);
        if (sample == null) throw new AssertionError("sample null");
        assertEquals(0, sample.getAxes().get(0), "CH1 center");
        assertEquals(1, sample.getStop(), "STOP");
        assertEquals(1, sample.getRec(), "REC");
        assertEquals("N", sample.getMode(), "mode");
    }

    private static void rejectsShortPacket() {
        if (Port40007RcReader.parsePacket(new byte[] { 1, 2, 3 }, 1_000L) != null) {
            throw new AssertionError("short packet should be rejected");
        }
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
```

- [ ] **Step 3: Run tests**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
```

Expected: parser tests pass.

- [ ] **Step 4: Commit 40007 reader**

Run:

```powershell
git add android/app/src/main/java/com/tunnathub/app/rc/Port40007RcReader.kt android/app/src/test/java/com/tunnathub/app/rc/Port40007RcReaderTest.java
git commit -m "feat(android): 解析 40007 低频 RC 输入"
```

## Task 5: Add App-to-V3s RC Uplink

**Files:**
- Create: `android/app/src/main/java/com/tunnathub/app/rc/RcUplink.kt`
- Modify: `ubuntu/src/rc_decode.h`
- Modify: `ubuntu/src/dji_rc.cpp`
- Modify: `ubuntu/src/web_server.cpp`

- [ ] **Step 1: Define uplink packet**

Use a new binary packet to avoid overloading existing V3s-to-App `RCM1`:

```text
magic: "RCA1" u32 little-endian
version: u16 = 1
size: u16 = 40
seq: u32
ts_ms: u64
ch[6]: i16 signed centered axes
buttons: u32 same bit order as RcMsg.kt button_bits
mode: u8 'S'/'N'/'F'/'?'
flags: u8 bit0=getevent_fresh bit1=p40007_fresh
reserved: u16
```

- [ ] **Step 2: Add Android sender**

Create `android/app/src/main/java/com/tunnathub/app/rc/RcUplink.kt`:

```kotlin
package com.tunnathub.app.rc

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder

class RcUplink(
    private val socket: DatagramSocket,
    private val host: InetAddress = InetAddress.getByName("10.0.0.1"),
    private val port: Int = PORT
) {
    private var seq = 0

    fun send(sample: RcInputSample, geteventFresh: Boolean, port40007Fresh: Boolean) {
        val buf = ByteBuffer.allocate(LENGTH).order(ByteOrder.LITTLE_ENDIAN)
        buf.putInt(MAGIC)
        buf.putShort(1)
        buf.putShort(LENGTH.toShort())
        buf.putInt(++seq)
        buf.putLong(sample.timestampMs)
        sample.axes.take(6).forEach { buf.putShort(it.toShort()) }
        buf.putInt(buttonBits(sample))
        buf.put(sample.mode.firstOrNull()?.code?.toByte() ?: '?'.code.toByte())
        var flags = 0
        if (geteventFresh) flags = flags or 1
        if (port40007Fresh) flags = flags or 2
        buf.put(flags.toByte())
        buf.putShort(0)
        socket.send(DatagramPacket(buf.array(), LENGTH, host, port))
    }

    companion object {
        const val PORT = 65531
        const val LENGTH = 40
        const val MAGIC = 0x31414352

        @JvmStatic
        fun buttonBits(sample: RcInputSample): Int =
            ((sample.stop and 1) shl 1) or
            ((sample.focus and 1) shl 2) or
            ((sample.shot and 1) shl 3) or
            ((sample.rec and 1) shl 4) or
            ((sample.c1 and 1) shl 6) or
            ((sample.c2 and 1) shl 7)
    }
}
```

- [ ] **Step 3: Add V3s receiver design**

In `ubuntu/src/rc_decode.h`, add enum value:

```c
typedef enum { RC_NONE = 0, RC_AE, RC_SPECIAL, RC_APP_FUSED } rc_type_t;
```

In `ubuntu/src/dji_rc.cpp`, add a non-blocking UDP socket on `65531`, parse `RCA1`, convert to `rc_state_t`, and feed it into the main loop as the freshest common source when `app_rc_age <= 80000us`.

- [ ] **Step 4: Preserve self-lock semantics**

In the main loop, ensure this ordering remains:

```cpp
rc_merge(..., &m);
if (app_rc_fresh) merge_app_rc(&m, app_rc_state);
advance_output_latches(m);
write_state_file(m, ...);
send_rcmsg(..., m, true, ...);
out_send(m);
```

Expected: latch advances exactly once from the final unified state.

- [ ] **Step 5: Expose diagnostics**

Add fields to `/tmp/dji_rc_state.json` and `/api/rc`:

```json
{
  "app_rc_good": 0,
  "app_rc_age_ms": 0,
  "getevent_hz": 0,
  "p40007_hz": 0,
  "active_rc_axis_source": "getevent"
}
```

- [ ] **Step 6: Commit uplink**

Run:

```powershell
git add android/app/src/main/java/com/tunnathub/app/rc/RcUplink.kt ubuntu/src/rc_decode.h ubuntu/src/dji_rc.cpp ubuntu/src/web_server.cpp
git commit -m "feat(rc): 添加 App 融合 RC 上行通道"
```

## Task 6: Wire Readers Into App Runtime

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
- Modify: `android/app/src/main/java/com/tunnathub/app/service/TunNatVpnService.kt`

- [ ] **Step 1: Add feature flag state**

In `MainActivity.kt`, add:

```kotlin
var rcFusionEnabled by remember { mutableStateOf(prefs.getBoolean("rc_fusion_enabled", false)) }
var rcFusionSource by remember { mutableStateOf("off") }
```

- [ ] **Step 2: Start reader coroutines when VPN is running**

Add a `LaunchedEffect(vpnRunning, rcFusionEnabled)` that starts:

```kotlin
val geteventReader = GetEventRcReader(axisMap = loadedAxisMap, onSample = { latestGetevent = it })
val p40007Reader = Port40007RcReader(socketFactory = { DatagramSocket(Port40007RcReader.PORT) }, onSample = { latest40007 = it })
val uplink = RcUplink(DatagramSocket())
```

Every 20ms, fuse latest samples and send one uplink packet:

```kotlin
val fused = RcFusionEngine.fuse(latestGetevent, latest40007, System.currentTimeMillis())
uplink.send(fused, fused.source.contains("getevent"), fused.source.contains("40007"))
```

- [ ] **Step 3: Update UI diagnostic text**

On the RC page, show:

```text
RC 输入: getevent+40007
getevent: 80-120Hz
40007: 5-20Hz
V3s uplink: online
```

Keep existing V3s `RcMsg` receiver as the downstream confirmation that V3s accepted and re-emitted the fused state.

- [ ] **Step 4: Commit runtime wiring**

Run:

```powershell
git add android/app/src/main/java/com/tunnathub/app/MainActivity.kt android/app/src/main/java/com/tunnathub/app/service/TunNatVpnService.kt
git commit -m "feat(android): 接入 RC 融合输入运行时"
```

## Task 7: Verification And PRD Update

**Files:**
- Modify: `.claude/prds/tun-nat-hub-core.prd.md`
- Modify: `docs/crsf_lua_bridge_plan.md`

- [ ] **Step 1: Build Android**

Run:

```powershell
cd android
.\gradlew.bat testDebugUnitTest
.\gradlew.bat assembleDebug
```

Expected: both commands end with `BUILD SUCCESSFUL`.

- [ ] **Step 2: Build V3s dji_rc**

Run:

```powershell
cmake --build tmp\build_aux_arm --target dji_rc
```

Expected: `dji_rc` binary is generated. If the cross toolchain is missing, install `gcc-arm-linux-gnueabihf` and `g++-arm-linux-gnueabihf`, then rerun the build.

- [ ] **Step 3: Deploy and read back**

Copy the test binary and APK with timestamped names, then read back hashes:

```powershell
adb -s 192.168.5.249:5555 install -r android\app\build\outputs\apk\debug\app-debug.apk
adb -s 192.168.5.249:5555 shell dumpsys package com.tunnathub.app | findstr version
```

For V3s, after copying `dji_rc`, verify:

```sh
md5sum /usr/local/bin/dji_rc
ps | grep dji_rc
```

- [ ] **Step 4: Field acceptance**

Run live checks:

```powershell
adb -s 192.168.5.249:5555 shell "timeout 5 getevent -lt"
adb -s 192.168.5.249:5555 shell "dumpsys package com.tunnathub.app | grep version"
curl http://192.168.144.66:8080/api/rc
```

Expected:

- `getevent_hz` is higher than 50Hz while sticks move.
- `p40007_hz` is lower but non-zero.
- Stick channels in `/api/rc` update smoothly from getevent.
- REC/STOP/FOCUS/SHOT keys still follow 40007.
- CH8/CH13 self-lock remains stable after button release.

- [ ] **Step 5: Update PRD**

Add to `.claude/prds/tun-nat-hub-core.prd.md`:

```markdown
- **RC 输入源升级**（2026-08-26）：摇杆高频数据优先来自 Android `getevent`，40007 端口作为低频摇杆 fallback 与按键/模式来源；V3s 仍以统一 RC 状态推进通道映射、自锁和 SBUS/CRSF 输出。
```

- [ ] **Step 6: Commit verification docs**

Run:

```powershell
git add .claude/prds/tun-nat-hub-core.prd.md docs/crsf_lua_bridge_plan.md
git commit -m "docs(rc): 更新 getevent 与 40007 融合验收标准"
```

## Self-Review

- Spec coverage: The plan covers both new facts: getevent high-frequency joystick and 40007 low-frequency joystick/key data. It keeps the existing unified RC state as the downstream source of truth, matching the previous self-lock fix.
- Risk gate: Task 1 explicitly verifies whether APK runtime can execute `getevent`; if not, implementation must switch to an approved sidecar or keep getevent as adb-only diagnostic.
- Testability: Fusion, getevent parsing, and 40007 parsing are pure unit-testable before touching runtime wiring.
- No raw capture commit: `tmp/` captures are intentionally left uncommitted unless needed, to avoid pushing noisy binary field logs.
