/**
 * frame.h — TUN_NAT_HUB 共享帧格式定义
 *
 * Android (Kotlin) 和 Ubuntu (C++) 共用此协议定义。
 * 两端的 frame_pack / frame_unpack 实现必须与此头文件保持一致。
 */

#ifndef TUN_NAT_HUB_FRAME_H
#define TUN_NAT_HUB_FRAME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── 帧格式常量 ───────────────────────────────────────────── */

#define FRAME_MAGIC_0     0x54   /* 'T' */
#define FRAME_MAGIC_1     0x4E   /* 'N' */
#define FRAME_MAGIC       0x544E /* 大端: "TN" */

#define FRAME_HEADER_LEN  4      /* Magic(2) + Length(2) */
#define FRAME_MAX_PAYLOAD 2048   /* 最大载荷字节数 */
#define FRAME_MAX_LEN     2052   /* FRAME_HEADER_LEN + FRAME_MAX_PAYLOAD */

/* ── 特殊帧约定 ───────────────────────────────────────────── */

/* 心跳帧: Length = 0，无 Payload。两端收到 PING 应立即回复同样的 PONG 帧。 */
/* Credit 帧: Length = 2，Payload 为大端序 2 字节 Credit 值（Phase 3 使用）。 */

/* ── 心跳参数 ──────────────────────────────────────────────── */

#define HEARTBEAT_INTERVAL_MS    1000   /* Ubuntu 端发送 PING 的间隔 */
#define HEARTBEAT_TIMEOUT_UBUNTU 3000   /* Ubuntu 判定断开的超时 */
#define HEARTBEAT_TIMEOUT_ANDROID 5000  /* Android 判定断开的超时 */

/* ── 帧打包 ─────────────────────────────────────────────────
 *
 * 将 payload 封装为帧写入 buf。
 * buf 必须至少有 (FRAME_HEADER_LEN + payload_len) 字节。
 *
 * 参数:
 *   buf         - 输出缓冲区（前 4 字节会被覆盖为帧头）
 *   payload_len - 载荷长度 (0 ~ FRAME_MAX_PAYLOAD)
 *
 * 返回: 完整的帧长度 (FRAME_HEADER_LEN + payload_len)
 */
static inline int frame_pack(uint8_t *buf, int payload_len) {
    buf[0] = FRAME_MAGIC_0;
    buf[1] = FRAME_MAGIC_1;
    buf[2] = (payload_len >> 8) & 0xFF;   /* 大端序高字节 */
    buf[3] = payload_len & 0xFF;           /* 大端序低字节 */
    return FRAME_HEADER_LEN + payload_len;
}

/* ── 帧解包 ─────────────────────────────────────────────────
 *
 * 从 buf 中校验并提取 payload。
 *
 * 参数:
 *   buf       - 输入缓冲区（含完整帧）
 *   total_len - buf 中有效数据的长度
 *   payload   - 输出: 指向 payload 开始的指针（buf + 4）
 *
 * 返回:
 *   >= 0 : payload 长度（字节数）
 *    -1  : Magic 不匹配
 *    -2  : Length 超过 FRAME_MAX_PAYLOAD
 *    -3  : 帧不完整 (total_len < FRAME_HEADER_LEN + payload_len)
 */
static inline int frame_unpack(uint8_t *buf, int total_len, uint8_t **payload) {
    if (total_len < FRAME_HEADER_LEN) return -3;

    /* 校验 Magic */
    if (buf[0] != FRAME_MAGIC_0 || buf[1] != FRAME_MAGIC_1) {
        return -1;
    }

    /* 解析长度（大端序） */
    int payload_len = ((int)buf[2] << 8) | (int)buf[3];

    /* 校验长度 */
    if (payload_len > FRAME_MAX_PAYLOAD) {
        return -2;
    }

    /* 校验完整性 */
    if (FRAME_HEADER_LEN + payload_len > total_len) {
        return -3;
    }

    if (payload != NULL) {
        *payload = buf + FRAME_HEADER_LEN;
    }

    return payload_len;
}

/* ── 判断是否为心跳帧 ─────────────────────────────────────── */

static inline int frame_is_heartbeat(int payload_len) {
    return payload_len == 0;
}

/* ── 判断是否为 Credit 帧 ─────────────────────────────────── */

static inline int frame_is_credit(int payload_len) {
    return payload_len == 2;
}

#ifdef __cplusplus
}
#endif

#endif /* TUN_NAT_HUB_FRAME_H */
