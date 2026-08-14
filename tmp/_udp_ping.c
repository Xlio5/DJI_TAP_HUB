/* 持续 CRSF Device_Ping 发送器: 每 200ms 发一次广播 ping, 持续 N 秒
 * 帧: [RCSF magic 4B][ee 04 28 00 ea crc]
 * 用法: udp_ping <ip> <port> <seconds> */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

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
    if (argc < 4) { fprintf(stderr, "usage: %s <ip> <port> <seconds>\n", argv[0]); return 1; }
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(atoi(argv[2]));
    inet_pton(AF_INET, argv[1], &a.sin_addr);

    unsigned char f[6] = {0xEE, 0x04, 0x28, 0x00, 0xEA, 0x00};
    f[5] = crc8(f + 2, 3);
    unsigned char pkt[4 + 6];
    memcpy(pkt, "\x52\x53\x43\x46", 4);  /* 网口 magic 0x46534352 LE, 与 App/固件一致 */
    memcpy(pkt + 4, f, 6);

    int secs = atoi(argv[3]);
    printf("ping %s: %02x %02x %02x %02x %02x %02x  x%d for %ds\n",
           argv[1], f[0], f[1], f[2], f[3], f[4], f[5], 5, secs);
    fflush(stdout);
    int sent = 0;
    for (int i = 0; i < secs * 5; i++) {
        sendto(fd, pkt, sizeof(pkt), 0, (struct sockaddr *)&a, sizeof(a));
        sent++;
        usleep(200000);
    }
    printf("done: sent %d pings\n", sent);
    return 0;
}
