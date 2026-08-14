/* 临时 UDP 发送工具: 从参数指定 IP/端口发 CRSF Device_Ping 帧
 * 正确帧 (参考 elrs_lua_python): [0xEE][4][0x28][0x00][0xEA][crc] */
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

/* CRC8 poly 0xD5 (CRSF), 对 frame[2..len-1] 计算 */
static unsigned char crc8(const unsigned char *data, int len) {
    unsigned char crc = 0;
    for (int i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++)
            crc = (crc & 0x80) ? ((crc << 1) ^ 0xD5) : (crc << 1);
    }
    return crc;
}

int main(int argc, char *argv[]) {
    if (argc < 3) { fprintf(stderr, "usage: %s <ip> <port>\n", argv[0]); return 1; }
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(atoi(argv[2]));
    inet_pton(AF_INET, argv[1], &a.sin_addr);
    /* CRSF Device_Ping 广播: addr=0xEE(TX模块) dest=0x00(广播) orig=0xEA(遥控) */
    unsigned char f[6] = {0xEE, 0x04, 0x28, 0x00, 0xEA, 0x00};
    f[5] = crc8(f + 2, 3);
    unsigned char pkt[4 + sizeof(f)];
    memcpy(pkt, "\x52\x53\x43\x46", 4);  /* 网口 magic 0x46534352 LE, 与 App/固件一致 */
    memcpy(pkt + 4, f, sizeof(f));
    printf("frame: ");
    for (int i = 0; i < 6; i++) printf("%02x ", f[i]);
    printf("\n");
    for (int i = 0; i < 5; i++) {
        sendto(fd, pkt, sizeof(pkt), 0, (struct sockaddr *)&a, sizeof(a));
        usleep(300000);
    }
    close(fd);
    printf("sent 5x %s:%s\n", argv[1], argv[2]);
    return 0;
}
