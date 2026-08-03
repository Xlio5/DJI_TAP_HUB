/*
 * CRSF 协议编解码 —— 纯 C, 可主机单元测试。
 *
 * 帧格式:
 *   [addr(1)] [len(1)] [type(1)] [payload(N)] [crc(1)]
 *   len = N + 2  (type + payload + crc), 整帧上限 62 字节
 *   CRC-8, poly 0xD5, init 0, 查表法, 覆盖 addr..payload 末尾(共 len 字节)
 *
 * 本模块复用 sbus_us_to_val() 的 172/992/1811 缩放:
 *   us(1000~2000) -> CRSF 11-bit 值(172~1811), 与 EdgeTX/BetaFlight 一致
 *
 * RC_CHANNELS_PACKED: 标准 22 通道 × 11bit = 242bit -> 31 字节 payload
 *   (前 16 通道为有效数据, 17-22 填 0)
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define CRSF_FRAME_MAX   62
#define CRSF_CH_PACKED   31   /* 22ch × 11bit = 242bit -> 31B payload */

/* 地址 */
#define CRSF_ADDR_FC            0xC0
#define CRSF_ADDR_TX            0xC8   /* 发射机 -> 接收机(下行) */
#define CRSF_ADDR_RX            0xEE   /* 接收机 -> 发射机(上行/回传) */
#define CRSF_ADDR_BROADCAST     0xEA

/* 帧类型 */
#define CRSF_FRAMETYPE_RC_CHANNELS_PACKED  0x16
#define CRSF_FRAMETYPE_LINK_STATISTICS     0x14
#define CRSF_FRAMETYPE_GPS                 0x02
#define CRSF_FRAMETYPE_BATTERY_SENSOR      0x08
#define CRSF_FRAMETYPE_ATTITUDE            0x1E
#define CRSF_FRAMETYPE_VARIO               0x07
#define CRSF_FRAMETYPE_FLIGHT_MODE         0x21
#define CRSF_FRAMETYPE_DEVICE_PING         0x1C
#define CRSF_FRAMETYPE_DEVICE_INFO         0x28
#define CRSF_FRAMETYPE_OPEN_TX_SYNC        0x10
#define CRSF_FRAMETYPE_ELRS_LINK_STATS     0x29   /* ELRS 变体 */

/* CRC-8 poly 0xD5 查表 */
extern const uint8_t crsf_crc8_table[256];
uint8_t crsf_crc8(const uint8_t *data, uint8_t len);

/* us(1000~2000) -> CRSF 11-bit(172~1811) —— 与 SBUS 同缩放, 复用 sbus_us_to_val */
uint16_t crsf_us_to_ch(uint16_t us);

/* 打包 RC_CHANNELS_PACKED 帧 (22 通道, 前16有效), 返回整帧长度 */
int crsf_pack_channels(const uint16_t ch_us[16], uint8_t out[CRSF_FRAME_MAX]);

/* 打包任意 CRSF 帧 (addr/type/payload), 返回整帧长度, <0 失败 */
int crsf_pack_frame(uint8_t addr, uint8_t type,
                    const uint8_t *payload, uint8_t plen,
                    uint8_t out[CRSF_FRAME_MAX]);

/* ── 接收状态机 ── */
typedef struct {
    uint8_t buf[CRSF_FRAME_MAX];
    uint8_t len;
    bool    synced;
} crsf_rx_t;

void crsf_rx_init(crsf_rx_t *rx);
/* 喂 1 字节。返回: 0=收集中, >0=完整帧长度(buf 内), -1=错误丢弃(自动重同步) */
int crsf_rx_byte(crsf_rx_t *rx, uint8_t b);

/* ── 回传遥测数据 ── */
typedef struct {
    uint32_t last_rx_us;         /* 最近一帧到达时刻(单调时钟, 微秒) */

    /* LINK_STATISTICS */
    int8_t   up_rssi1, up_rssi2, up_snr;
    uint8_t  up_quality;
    int8_t   dn_rssi1, dn_rssi2, dn_snr;
    uint8_t  dn_quality;

    /* GPS */
    bool     has_gps;
    int32_t  lat_degE7, lon_degE7;      /* ×1e-7 度 */
    uint16_t gps_speed_kmh10;           /* ×10 km/h */
    uint16_t gps_heading_deg10;         /* ×10 度 */
    int32_t  gps_alt_mm;                /* mm */
    uint8_t  gps_sats;

    /* BATTERY */
    bool     has_batt;
    uint16_t batt_voltage_mV10;         /* ×10 mV (如 126.0V -> 1260) */
    uint16_t batt_current_mA10;         /* ×10 mA */
    uint32_t batt_capacity_mAh;
    uint8_t  batt_remaining_pct;

    /* ATTITUDE */
    bool     has_att;
    int16_t  att_pitch_deg100;          /* ×100 度 */
    int16_t  att_roll_deg100;
    int16_t  att_yaw_deg100;

    /* VARIO */
    bool     has_vario;
    int32_t  vario_cms;                 /* cm/s 垂直速度 */

    /* FLIGHT_MODE */
    bool     has_fmode;
    char     flight_mode[24];
} crsf_telem_t;

/* 解析一帧(buf, len) 填充 telem。认识的帧返回 true, 否则 false。 */
bool crsf_parse_frame(const uint8_t *buf, uint8_t len, crsf_telem_t *telem);
