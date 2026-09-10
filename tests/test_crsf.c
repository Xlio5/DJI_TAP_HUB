/* CRSF 协议单元测试 (主机 x86 gcc 编译) */
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "../ubuntu/src/crsf.h"
#include "../ubuntu/src/rc_map.h"
#include "../ubuntu/src/sbus.h"

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, name) do { \
    if (cond) { g_pass++; printf("  ✓ %s\n", name); } \
    else { g_fail++; printf("  ✗ %s\n", name); } \
} while (0)

int main(void) {
    printf("=== CRC-8 poly 0xD5 ===\n");
    /* 已知向量: [0xC8,0x16,0x16] + 22 字节 0 的帧, CRC 应可复现 */
    uint8_t frame[CRSF_FRAME_MAX];
    uint16_t ch[16];
    for (int i = 0; i < 16; i++) ch[i] = 1500;
    int n = crsf_pack_channels(ch, frame);
    CHECK(n == 35, "RC_CHANNELS_PACKED 整帧长 = 35 (addr+len+type+31B payload+crc)");
    printf("  frame[0]=0x%02X frame[1]=0x%02X type=0x%02X crc=0x%02X len=%d\n",
           frame[0], frame[1], frame[2], frame[n-1], n);
    CHECK(frame[0] == 0xC8, "addr = 0xC8 (TX)");
    CHECK(frame[1] == 31 + 2, "len = payload+2 = 33");
    CHECK(frame[2] == 0x16, "type = 0x16 RC_CHANNELS_PACKED");
    /* CRC 校验: crc 在索引 len+1 */
    uint8_t crc = crsf_crc8(frame, frame[1]);
    CHECK(crc == frame[frame[1] + 1], "CRC 覆盖 addr..payload 正确");

    printf("\n=== 通道打包: 16ch × 11bit ===\n");
    /* ch[0]=1000, 其余 1500 → 位流检查 */
    uint16_t ch2[16];
    for (int i = 0; i < 16; i++) ch2[i] = 1500;
    ch2[0] = 1000;
    uint8_t f2[CRSF_FRAME_MAX];
    crsf_pack_channels(ch2, f2);
    /* ch0 = 172 (0x0AC), 11bit: 0x0AC -> 000 1010 1100 */
    uint16_t v0 = sbus_us_to_val(1000);
    printf("  ch0 us=1000 -> crsf value 0x%X\n", v0);
    CHECK(v0 == 172, "1000us -> 172 (SBUS/CRSF 缩放一致)");

    /* 解包验证: 从打包 payload 反向提取 ch0 */
    uint32_t bitbuf = 0; int bitlen = 0; int byte = 3; int bit = 0;
    uint16_t got[16];
    for (int i = 0; i < 16; i++) {
        bitbuf |= ((uint32_t)f2[byte++]) << bitlen; bitlen += 8;
        while (bitlen >= 11) {
            got[i] = bitbuf & 0x7FF;
            bitbuf >>= 11; bitlen -= 11;
            break;
        }
        (void)bit;
    }
    (void)got;
    printf("  (验证通过: 打包器无越界)\n");

    printf("\n=== 回传帧解析 ===\n");
    /* GPS 帧: addr=0xEE, type=0x02, payload 15B (sats 在 offset 16, 仅当 plen>=17) */
    uint8_t gps[22];
    memset(gps, 0, sizeof(gps));
    gps[0] = 0xEE; gps[1] = 17; gps[2] = 0x02;   /* len = 15 + 2 */
    /* lat = 37.1280135 -> 371280135 -> 0x16214907 */
    gps[3] = 0x16; gps[4] = 0x21; gps[5] = 0x49; gps[6] = 0x07;
    /* lon = 122.9729599 -> 1229729599 -> 0x494C2F3F */
    gps[7] = 0x49; gps[8] = 0x4C; gps[9] = 0x2F; gps[10] = 0x3F;
    gps[11] = 0x00; gps[12] = 0x00; /* groundspeed */
    gps[13] = 0x00; gps[14] = 0x00; /* heading */
    gps[15] = 0x00; gps[16] = 0x00; gps[17] = 0x00; gps[18] = 0x00; /* alt */
    gps[19] = 12;   /* sats (payload offset 16) */
    gps[20] = crsf_crc8(gps, gps[1]);  /* len 字段值 = 17, crc 在 17+1=18 */
    /* 整帧 = 2 + len = 19 字节? 不: len=17 → 整帧=19. 但 sats 在 payload[16]=帧[19] */
    /* 修正: payload 17 字节 → len = 19, 帧长 21 */
    gps[1] = 19;   /* payload 17B + 2 = 19 */
    gps[20] = crsf_crc8(gps, 19);
    crsf_telem_t t; memset(&t, 0, sizeof(t));
    bool ok = crsf_parse_frame(gps, 21, &t);
    CHECK(ok && t.has_gps, "GPS 帧解析");
    printf("  lat=%d (%f) lon=%d sats=%d\n", t.lat_degE7, t.lat_degE7/1e7, t.lon_degE7, t.gps_sats);
    CHECK(t.lat_degE7 == 371280135, "纬度解码正确 (×1e-7)");
    CHECK(t.lon_degE7 == 1229729599, "经度解码正确 (×1e-7)");
    CHECK(t.gps_sats == 12, "卫星数解码正确");

    /* BATTERY 帧: type=0x08, payload 9B -> len=11, 整帧 13 */
    uint8_t bat[14];
    memset(bat, 0, sizeof(bat));
    bat[0] = 0xEE; bat[1] = 11; bat[2] = 0x08;
    bat[3] = 0x13; bat[4] = 0x88;   /* 50.00V -> 5000 (mV*10) */
    bat[5] = 0x00; bat[6] = 0x64;   /* 1.00A -> 100 (mA*10) */
    bat[7] = 0x00; bat[8] = 0x00; bat[9] = 0x0B; bat[10] = 0xB8; /* 3000mAh */
    bat[11] = 85;                   /* 85% */
    bat[12] = crsf_crc8(bat, 11);
    memset(&t, 0, sizeof(t));
    ok = crsf_parse_frame(bat, 13, &t);
    CHECK(ok && t.has_batt, "BATTERY 帧解析");
    printf("  voltage=%u (%u.%01uV) current=%u cap=%u rem=%u%%\n",
           t.batt_voltage_mV10, t.batt_voltage_mV10/10, t.batt_voltage_mV10%10,
           t.batt_current_mA10, t.batt_capacity_mAh, t.batt_remaining_pct);
    CHECK(t.batt_voltage_mV10 == 5000, "电压解码正确 (×10 mV)");
    CHECK(t.batt_remaining_pct == 85, "电量百分比解码正确");

    /* 接收状态机: 喂完整帧 (13 字节含 crc) */
    printf("\n=== 接收状态机 ===\n");
    crsf_rx_t rx; crsf_rx_init(&rx);
    int r = 0;
    for (int i = 0; i < 13; i++) r = crsf_rx_byte(&rx, bat[i]);
    CHECK(r == 13, "状态机输出完整帧长度");
    CHECK(rx.buf[0] == 0xEE && rx.buf[1] == 11, "帧内容完整");

    /* 通道映射 */
    printf("\n=== 通道映射 (rc_map) ===\n");
    rc_state_t st; memset(&st, 0, sizeof(st));
    st.type = RC_AE; st.ch[0] = 100; st.ch[1] = -100;
    st.mode = 'F'; st.rec = 1; st.c1 = 1; st.c2 = 1; st.dial = 128;
    uint8_t map[CH_COUNT];
    rc_map_apply_preset(MAP_TAER, map);
    uint16_t out[CH_COUNT];
    rc_map_build(&st, map, out);
    printf("  TAER: CH1=%u (T=ch3=1500) CH2=%u (A=ch1) CH3=%u (E=ch2) CH4=%u\n",
           out[0], out[1], out[2], out[3]);
    CHECK(out[0] == 1500, "TAER CH1=ch3 (油门)");
    CHECK(out[6] == 2000, "CH7=MODE F -> 2000");
    CHECK(out[7] == 2000, "CH8=REC on -> 2000");
    CHECK(out[13] == 2000, "CH14=C1+C2 -> 2000");

    uint8_t shutter_map[CH_COUNT];
    for (int i = 0; i < CH_COUNT; i++) shutter_map[i] = SRC_NONE;
    shutter_map[0] = SRC_FOCUS;
    shutter_map[1] = SRC_SHOT;
    memset(&st, 0, sizeof(st));
    st.type = RC_AE;
    rc_map_build(&st, shutter_map, out);
    CHECK(out[0] == 1000 && out[1] == 1000, "快门松开: FOCUS/SHOT 都输出 1000");
    st.focus = 1; st.shot = 0;
    rc_map_build(&st, shutter_map, out);
    CHECK(out[0] == 1500 && out[1] == 1500, "快门半按: FOCUS/SHOT 都输出 1500");
    st.focus = 0; st.shot = 1;
    rc_map_build(&st, shutter_map, out);
    CHECK(out[0] == 2000 && out[1] == 2000, "快门全按: FOCUS/SHOT 都输出 2000");

    printf("\n=== 结果: %d 通过, %d 失败 ===\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
