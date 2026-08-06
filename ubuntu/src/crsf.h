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

/* 地址 (CRSF 官方标准, 对照 ax12 逆向) */
#define CRSF_ADDR_FC            0xC0   /* Flight controller 飞控 */
#define CRSF_ADDR_TX            0xC8   /* CRSF_TRANSMITTER, 下行源 (兼容现有) */
#define CRSF_ADDR_CRSF_RX       0xEA   /* CRSF_RECEIVER 接收机 (回传源/广播) */
#define CRSF_ADDR_RC_RX         0xEC   /* RC receiver */
#define CRSF_ADDR_RADIO_TX      0xEE   /* Radio_Transmitter 遥控器 (V3s 扮演角色) */
#define CRSF_ADDR_BROADCAST     0xEA   /* 广播 (与 CRSF_RECEIVER 同值) */
#define CRSF_ADDR_USB           0x10

/* 帧类型 (CRSF 官方规范 + ax12 逆向对照)
 * 广播帧 (0x02-0x27): [addr][len][type][payload][crc]
 * 扩展头帧 (0x28-0x96): [addr][len][type][dest][orig][payload][crc] — 多点寻址/配置 */
#define CRSF_FRAMETYPE_GPS                   0x02
#define CRSF_FRAMETYPE_VARIO                 0x07
#define CRSF_FRAMETYPE_BATTERY_SENSOR        0x08
#define CRSF_FRAMETYPE_HEARTBEAT             0x0B
#define CRSF_FRAMETYPE_OPEN_TX_SYNC          0x10
#define CRSF_FRAMETYPE_LINK_STATISTICS       0x14
#define CRSF_FRAMETYPE_RC_CHANNELS_PACKED    0x16
#define CRSF_FRAMETYPE_SUBSET_RC_CHANNELS    0x17
#define CRSF_FRAMETYPE_11_BITS               0x18
#define CRSF_FRAMETYPE_ATTITUDE              0x1E
#define CRSF_FRAMETYPE_FLIGHT_MODE           0x21
/* 扩展头帧 (0x28+) */
#define CRSF_FRAMETYPE_DEVICE_PING           0x28
#define CRSF_FRAMETYPE_DEVICE_INFO           0x29
#define CRSF_FRAMETYPE_PARAMETER_SETTINGS_ENTRY 0x2B
#define CRSF_FRAMETYPE_PARAMETER_READ        0x2C
#define CRSF_FRAMETYPE_PARAMETER_WRITE       0x2D
#define CRSF_FRAMETYPE_COMMAND               0x32
#define CRSF_FRAMETYPE_MAV_LINK              0x30
#define CRSF_FRAMETYPE_MAV_FC                0x31

/* ELRS 链路统计: ELRS 发射机用 0x14 标准帧, RX 侧扩展字段在 payload 内 */
#define CRSF_FRAMETYPE_ELRS_LINK_STATS       CRSF_FRAMETYPE_LINK_STATISTICS

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

/* 打包扩展头帧 (0x28+, 含 dest/orig 两字节):
 *   [addr][len][type][dest][orig][payload][crc]
 * dest=目标设备地址, orig=源设备地址。返回整帧长度, <0 失败 */
int crsf_pack_ext_frame(uint8_t addr, uint8_t type, uint8_t dest, uint8_t orig,
                        const uint8_t *payload, uint8_t plen,
                        uint8_t out[CRSF_FRAME_MAX]);

/* Heartbeat 帧: [0xC8][len=4][0x0B][dev_hi][dev_lo][CRC] (逆向 D.i) */
int crsf_pack_heartbeat(uint8_t dev_hi, uint8_t dev_lo, uint8_t out[CRSF_FRAME_MAX]);

/* Device_Ping: [addr][len][type][dest][orig][CRC] — 设备发现 (扩展头) */
int crsf_pack_device_ping(uint8_t dest, uint8_t orig, uint8_t out[CRSF_FRAME_MAX]);

/* ── 接收状态机 ── */
typedef struct {
    uint8_t buf[CRSF_FRAME_MAX];
    uint8_t len;
    bool    synced;
} crsf_rx_t;

void crsf_rx_init(crsf_rx_t *rx);
/* 喂 1 字节。返回: 0=收集中, >0=完整帧长度(buf 内), -1=错误丢弃(自动重同步) */
int crsf_rx_byte(crsf_rx_t *rx, uint8_t b);

/* ── 参数协议 (ELRS Lua 配置, 对照逆向 I.c + elrsV3.lua) ── */
#define CRSF_PARAM_HIDDEN     0x80   /* 参数类型 bit7 = hidden */
#define CRSF_PARAM_ROOT       0xFF   /* 父 id = 根 */

typedef enum {
    CRSF_PTYPE_UINT8    = 0,
    CRSF_PTYPE_INT8     = 1,
    CRSF_PTYPE_UINT16   = 2,
    CRSF_PTYPE_INT16    = 3,
    CRSF_PTYPE_UINT32   = 4,
    CRSF_PTYPE_INT32    = 5,
    CRSF_PTYPE_FLOAT    = 8,
    CRSF_PTYPE_TEXT_SEL = 9,
    CRSF_PTYPE_STRING   = 10,
    CRSF_PTYPE_FOLDER   = 11,
    CRSF_PTYPE_INFO     = 12,
    CRSF_PTYPE_COMMAND  = 13,
    CRSF_PTYPE_OUT_OF_RANGE = 0x7F
} crsf_param_type_t;

/* 参数条目 (Settings_Entry 0x2B 解析结果) */
typedef struct {
    uint8_t id;
    uint8_t parent;
    uint8_t type;              /* crsf_param_type_t (含 hidden bit) */
    uint8_t flags;
    uint8_t min[4];            /* 值域最小 (按类型宽度) */
    uint8_t max[4];            /* 值域最大 */
    uint8_t def[4];            /* 默认值 */
    char     unit[7];          /* 单位 (NUL 结尾) */
    char     name[17];         /* 名称 (NUL 结尾) */
} crsf_param_entry_t;

/* 解析 Settings_Entry payload → crsf_param_entry_t */
void crsf_param_parse_entry(const uint8_t *pl, uint8_t plen, crsf_param_entry_t *e);

/* Device_Info (0x29) 响应: 设备名/版本/参数数 (扩展头) 打包 */
int crsf_pack_device_info(const char *name, uint8_t serial_hi, uint8_t serial_lo,
                          uint8_t hw_ver, uint8_t sw_ver,
                          uint8_t num_params, uint8_t proto_ver,
                          uint8_t out[CRSF_FRAME_MAX]);

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
