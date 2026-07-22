/*
 * DJI 遥控器摇杆/按键解码层 —— 纯 C,无 ESP-IDF 依赖,可主机单元测试。
 *
 * 支持两种 RC 数据帧(按 cmd_set/cmd_id 由调用方分派):
 *   - RC/0xAE      (cmd_set=6, cmd_id=0xAE)  RC Plus 2,17B payload
 *   - SPECIAL/0x02 (cmd_set=1, cmd_id=0x02)  旧版遥控器,13B payload
 *
 * 测试接口(脱离硬件可直接喂 payload 字节):
 *   decode_rc_ae() / decode_special_02()  —— payload -> rc_state_t
 *   rc_state_to_kv()                       —— rc_state_t -> 紧凑 KV 字符串
 *
 * 逻辑移植自 dji_mid_live.py 的 decode_rc_ae / decode_special_02
 * 及 dji_duml_parser.py 的 print_rc_ae 按键位分解。
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

typedef enum { RC_NONE = 0, RC_AE, RC_SPECIAL } rc_type_t;

typedef struct {
    rc_type_t type;
    int16_t   ch[6];        /* 6 通道,已减中位:signed = raw - 1024 */

    /* 两种帧共有的按键/开关 */
    uint8_t   btn;          /* 主/中心键 */
    uint8_t   stop;
    uint8_t   focus;
    uint8_t   shot;
    uint8_t   rec;
    char      mode;         /* 'S' / 'N' / 'F' / '?' */

    /* RC/0xAE 专有 */
    uint8_t   rth;
    uint8_t   up, down, left, right;
    uint8_t   aircraft, back;
    uint8_t   c1, c2, c3;
    uint8_t   dial;
} rc_state_t;

bool decode_rc_ae(const uint8_t *pl, int pl_len, rc_state_t *st);
bool decode_special_02(const uint8_t *pl, int pl_len, rc_state_t *st);

const char *rc_type_name(rc_type_t t);

/* 把解码字段格式化成紧凑 KV(不含端口/计数前后缀)。返回写入的字符数。 */
int rc_state_to_kv(const rc_state_t *st, char *out, size_t n);

/*
 * 把两路解码状态融合成一条(逐字段择新)。
 *   - 公共字段(6通道 / MODE / STOP / FOCUS / SHOT / REC):
 *       取更新鲜(age 更小)的一路。
 *   - RC/0xAE 专有字段(BTN/C1/C2/C3/DIAL/RTH/UP/DN/L/R/AC/BACK):
 *       取更新鲜的 RC/0xAE 那一路;若两路都没有 RC/0xAE 帧则置 0。
 *       (中心键 BTN 也归此组: SPECIAL 那路的 pl[11]&1 实为 C3,不可当中心键)
 * age_*_us: 各路数据的"年龄"(微秒,越小越新)。type==RC_NONE 表示该路暂无数据。
 * stale_us: 超时阈值(微秒)。age 超过它的一路视为失效(不参与融合),
 *           使掉线那路的字段回落到中性(0),避免旧值被永久锁存。
 * out->type: 若融合结果含 RC/0xAE 专有字段则为 RC_AE(使 KV 打印额外字段),
 *            否则为公共字段来源那一路的类型;两路都失效则 RC_NONE。
 */
void rc_merge(const rc_state_t *a, int64_t age_a_us,
              const rc_state_t *b, int64_t age_b_us,
              int64_t stale_us, rc_state_t *out);
