#ifdef __cplusplus
extern "C" {
#endif
/*
 * DUML 协议解析层 —— 纯 C,无 ESP-IDF 依赖,可在主机上单元测试。
 *
 * 测试接口(可脱离硬件直接调用):
 *   duml_parse()  —— 对一段缓冲区做帧同步 + CRC 校验,产出包头信息
 *   duml_crc8()   —— 头部 CRC-8 (seed 0x77)
 *   duml_crc16()  —— 整包 CRC-16 (seed 0x3692)
 *
 * 逻辑移植自 dji_mid_live.py / dji_duml_parser.py / esp32_dji_sbus main.cpp。
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>

#define DUML_SOF            0x55
#define DUML_MIN_PKT        13      /* 最短合法包长 */
#define DUML_MAX_PKT        1024
#define DUML_HDR_CRC8_SEED  0x77
#define DUML_CRC16_SEED     0x3692

typedef struct {
    int            pkt_len;      /* 整包字节数 */
    uint8_t        cmd_set;      /* buf[9]  命令集 */
    uint8_t        cmd_id;       /* buf[10] 命令ID */
    const uint8_t *payload;      /* 指向 buf 内部(buf[11]) */
    int            payload_len;  /* pkt_len - 13 */
} duml_pkt_t;

/*
 * 尝试从 buf 起始处解析一个 DUML 包。
 * 返回值:
 *    >0  成功,值为 pkt_len,*out 已填充(调用方应消费 pkt_len 字节)
 *     0  此偏移非法(非 SOF / 长度非法 / CRC 不过)—— 调用方前进 1 字节重同步
 *    -1  数据不足,需要更多字节(SOF 合理但整包未到齐)—— 调用方保留并等待
 */
int duml_parse(const uint8_t *buf, int buf_len, duml_pkt_t *out);

uint8_t  duml_crc8(const uint8_t *p, int n, uint8_t seed);
uint16_t duml_crc16(const uint8_t *p, int n, uint16_t seed);
#ifdef __cplusplus
}
#endif
