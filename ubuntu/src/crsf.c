/* CRSF 协议编解码实现 —— 见 crsf.h。纯 C。 */
#include "crsf.h"
#include "sbus.h"   /* 复用 sbus_us_to_val 的 us->11bit 缩放 */
#include <string.h>

/* ── CRC-8 poly 0xD5 查表 (crc = 0; do crc=tab[crc^b] while(...)) ── */
const uint8_t crsf_crc8_table[256] = {
    0x00,0xD5,0x7F,0xAA,0xFE,0x2B,0x81,0x54,0x29,0xFC,0x56,0x83,0xD7,0x02,0xA8,0x7D,
    0x52,0x87,0x2D,0xF8,0xAC,0x79,0xD3,0x06,0x7B,0xAE,0x04,0xD1,0x85,0x50,0xFA,0x2F,
    0xA4,0x71,0xDB,0x0E,0x5A,0x8F,0x25,0xF0,0x8D,0x58,0xF2,0x27,0x73,0xA6,0x0C,0xD9,
    0xF6,0x23,0x89,0x5C,0x08,0xDD,0x77,0xA2,0xDF,0x0A,0xA0,0x75,0x21,0xF4,0x5E,0x8B,
    0x9D,0x48,0xE2,0x37,0x63,0xB6,0x1C,0xC9,0xB4,0x61,0xCB,0x1E,0x4A,0x9F,0x35,0xE0,
    0xCF,0x1A,0xB0,0x65,0x31,0xE4,0x4E,0x9B,0xE6,0x33,0x99,0x4C,0x18,0xCD,0x67,0xB2,
    0x39,0xEC,0x46,0x93,0xC7,0x12,0xB8,0x6D,0x10,0xC5,0x6F,0xBA,0xEE,0x3B,0x91,0x44,
    0x6B,0xBE,0x14,0xC1,0x95,0x40,0xEA,0x3F,0x42,0x97,0x3D,0xE8,0xBC,0x69,0xC3,0x16,
    0xEF,0x3A,0x90,0x45,0x11,0xC4,0x6E,0xBB,0xC6,0x13,0xB9,0x6C,0x38,0xED,0x47,0x92,
    0xBD,0x68,0xC2,0x17,0x43,0x96,0x3C,0xE9,0x94,0x41,0xEB,0x3E,0x6A,0xBF,0x15,0xC0,
    0x4B,0x9E,0x34,0xE1,0xB5,0x60,0xCA,0x1F,0x62,0xB7,0x1D,0xC8,0x9C,0x49,0xE3,0x36,
    0x19,0xCC,0x66,0xB3,0xE7,0x32,0x98,0x4D,0x30,0xE5,0x4F,0x9A,0xCE,0x1B,0xB1,0x64,
    0x72,0xA7,0x0D,0xD8,0x8C,0x59,0xF3,0x26,0x5B,0x8E,0x24,0xF1,0xA5,0x70,0xDA,0x0F,
    0x20,0xF5,0x5F,0x8A,0xDE,0x0B,0xA1,0x74,0x09,0xDC,0x76,0xA3,0xF7,0x22,0x88,0x5D,
    0xD6,0x03,0xA9,0x7C,0x28,0xFD,0x57,0x82,0xFF,0x2A,0x80,0x55,0x01,0xD4,0x7E,0xAB,
    0x84,0x51,0xFB,0x2E,0x7A,0xAF,0x05,0xD0,0xAD,0x78,0xD2,0x07,0x53,0x86,0x2C,0xF9,
};

uint8_t crsf_crc8(const uint8_t *data, uint8_t len) {
    uint8_t crc = 0;
    for (uint8_t i = 0; i < len; i++)
        crc = crsf_crc8_table[crc ^ data[i]];
    return crc;
}

/* us(1000~2000) -> CRSF 11-bit(172~1811), 与 SBUS 同缩放 */
uint16_t crsf_us_to_ch(uint16_t us) {
    return sbus_us_to_val(us);
}

/* 打包 RC_CHANNELS_PACKED: 22 通道 × 11bit, 前 16 有效, 17-22=0 */
int crsf_pack_channels(const uint16_t ch_us[16], uint8_t out[CRSF_FRAME_MAX]) {
    uint8_t payload[CRSF_CH_PACKED];
    memset(payload, 0, sizeof(payload));

    /* 16 通道 11bit 连续位流 */
    uint32_t bitbuf = 0;
    int bitlen = 0, byte = 0, bit = 0;
    for (int i = 0; i < 16; i++) {
        uint32_t v = crsf_us_to_ch(ch_us[i]) & 0x7FF;   /* 11-bit */
        bitbuf |= v << bitlen;
        bitlen += 11;
        while (bitlen >= 8) {
            payload[byte++] = (uint8_t)(bitbuf & 0xFF);
            bitbuf >>= 8;
            bitlen -= 8;
        }
        (void)bit;
    }
    if (bitlen > 0) payload[byte++] = (uint8_t)(bitbuf & 0xFF);
    /* 22 通道: 剩 6 通道为 0, 已由 memset 填充 */

    return crsf_pack_frame(CRSF_ADDR_TX, CRSF_FRAMETYPE_RC_CHANNELS_PACKED,
                           payload, CRSF_CH_PACKED, out);
}

int crsf_pack_frame(uint8_t addr, uint8_t type,
                    const uint8_t *payload, uint8_t plen,
                    uint8_t out[CRSF_FRAME_MAX]) {
    if (plen > 60) return -1;
    uint8_t len = (uint8_t)(plen + 2);   /* type + payload + crc */
    out[0] = addr;
    out[1] = len;
    out[2] = type;
    if (plen) memcpy(out + 3, payload, plen);
    out[len + 1] = crsf_crc8(out, len);  /* crc 在索引 len+1 */
    return (int)len + 2;                 /* 整帧 = addr + len + len 字节 = 2 + len */
}

/* 扩展头帧: [addr][len][type][dest][orig][payload][crc]
 * CRC 覆盖 addr..payload 末尾 (共 len 字节: type+dest+orig+payload+crc) */
int crsf_pack_ext_frame(uint8_t addr, uint8_t type, uint8_t dest, uint8_t orig,
                        const uint8_t *payload, uint8_t plen,
                        uint8_t out[CRSF_FRAME_MAX]) {
    if (plen > 58) return -1;   /* 扩展头多 2 字节, payload 上限 58 */
    uint8_t len = (uint8_t)(plen + 4);   /* type + dest + orig + payload + crc */
    out[0] = addr;
    out[1] = len;
    out[2] = type;
    out[3] = dest;
    out[4] = orig;
    if (plen) memcpy(out + 5, payload, plen);
    out[len + 1] = crsf_crc8(out, len);  /* crc 在索引 len+1 */
    return (int)len + 2;
}

/* Heartbeat: [0xC8][4][0x0B][dev_hi][dev_lo][CRC]
 * len = 4 = type + dev_hi + dev_lo + crc */
int crsf_pack_heartbeat(uint8_t dev_hi, uint8_t dev_lo, uint8_t out[CRSF_FRAME_MAX]) {
    uint8_t pl[2] = {dev_hi, dev_lo};
    return crsf_pack_frame(CRSF_ADDR_RADIO_TX, CRSF_FRAMETYPE_HEARTBEAT, pl, 2, out);
}

/* Device_Ping (扩展头): 广播发现, dest=目标/0 广播, orig=源 */
int crsf_pack_device_ping(uint8_t dest, uint8_t orig, uint8_t out[CRSF_FRAME_MAX]) {
    return crsf_pack_ext_frame(CRSF_ADDR_RADIO_TX, CRSF_FRAMETYPE_DEVICE_PING,
                               dest, orig, NULL, 0, out);
}

void crsf_rx_init(crsf_rx_t *rx) {
    memset(rx, 0, sizeof(*rx));
}

int crsf_rx_byte(crsf_rx_t *rx, uint8_t b) {
    if (rx->len >= CRSF_FRAME_MAX) {   /* 溢出, 重新同步 */
        rx->len = 0;
        rx->synced = false;
    }
    rx->buf[rx->len++] = b;

    if (!rx->synced) {
        if (rx->len >= 2) {
            /* 帧长字段: len = payload + 2, 合法 3..62 */
            if (rx->buf[1] < 3 || rx->buf[1] > 60) {
                /* 丢弃第一字节, 继续扫描同步 */
                memmove(rx->buf, rx->buf + 1, rx->len - 1);
                rx->len--;
                return -1;
            }
            rx->synced = true;
        }
        return 0;
    }

    uint8_t flen = rx->buf[1];
    if (flen + 2 > rx->len) return 0;               /* 未收满: addr+len+len+1(crc) */
    if (crsf_crc8(rx->buf, flen) == rx->buf[flen + 1]) { /* CRC 在 flen+1 */
        uint8_t got = flen + 2;                     /* 整帧字节数 */
        /* 平移剩余字节供下一个帧 */
        uint8_t rest = rx->len - got;
        memmove(rx->buf, rx->buf + got, rest);
        rx->len = rest;
        rx->synced = false;
        return (int)got;                             /* 完整帧 */
    }
    /* CRC 失败, 重新同步 */
    rx->len = 0;
    rx->synced = false;
    return -1;
}

/* ── 帧解析 (回传) ── */
static uint16_t rd_u16be(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t rd_u32be(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

bool crsf_parse_frame(const uint8_t *buf, uint8_t len, crsf_telem_t *telem) {
    if (len < 4) return false;
    uint8_t type = buf[2];
    const uint8_t *pl = buf + 3;
    uint8_t plen = len - 4;

    switch (type) {
    case CRSF_FRAMETYPE_LINK_STATISTICS: {   /* ELRS_LINK_STATS 同值 0x14 */
        if (plen < 8) return false;
        telem->up_rssi1  = (int8_t)pl[0];
        telem->up_rssi2  = (int8_t)pl[1];
        telem->up_snr    = (int8_t)pl[2];
        telem->up_quality = pl[3];
        telem->dn_rssi1  = (int8_t)pl[4];
        telem->dn_rssi2  = (int8_t)pl[5];
        telem->dn_snr    = (int8_t)pl[6];
        telem->dn_quality = pl[7];
        return true;
    }
    case CRSF_FRAMETYPE_GPS: {
        if (plen < 15) return false;
        telem->has_gps = true;
        /* 经纬度: 有符号 int32 BE × 1e-7 */
        int32_t lat = (int32_t)rd_u32be(pl);
        int32_t lon = (int32_t)rd_u32be(pl + 4);
        if (lat == 0 && lon == 0) { telem->has_gps = false; return false; }
        telem->lat_degE7 = lat;
        telem->lon_degE7 = lon;
        telem->gps_speed_kmh10    = rd_u16be(pl + 8);   /* ×10 km/h */
        telem->gps_heading_deg10  = rd_u16be(pl + 10);  /* ×10 度 */
        telem->gps_alt_mm         = (int32_t)rd_u32be(pl + 12); /* mm */
        if (plen >= 17) telem->gps_sats = pl[16];
        return true;
    }
    case CRSF_FRAMETYPE_BATTERY_SENSOR: {
        if (plen < 8) return false;
        telem->has_batt = true;
        telem->batt_voltage_mV10   = rd_u16be(pl);      /* ×10 mV */
        telem->batt_current_mA10   = rd_u16be(pl + 2);  /* ×10 mA */
        telem->batt_capacity_mAh   = rd_u32be(pl + 4);  /* mAh */
        if (plen >= 9) telem->batt_remaining_pct = pl[8];
        return true;
    }
    case CRSF_FRAMETYPE_ATTITUDE: {
        if (plen < 6) return false;
        telem->has_att = true;
        telem->att_pitch_deg100 = (int16_t)rd_u16be(pl);      /* ×100 度 */
        telem->att_roll_deg100  = (int16_t)rd_u16be(pl + 2);
        telem->att_yaw_deg100   = (int16_t)rd_u16be(pl + 4);
        return true;
    }
    case CRSF_FRAMETYPE_VARIO: {
        if (plen < 4) return false;
        telem->has_vario = true;
        telem->vario_cms = (int32_t)rd_u32be(pl);             /* cm/s */
        return true;
    }
    case CRSF_FRAMETYPE_FLIGHT_MODE: {
        size_t n = plen < sizeof(telem->flight_mode) - 1 ? plen : sizeof(telem->flight_mode) - 1;
        memcpy(telem->flight_mode, pl, n);
        telem->flight_mode[n] = '\0';
        telem->has_fmode = true;
        return true;
    }
    default:
        return false;
    }
}
