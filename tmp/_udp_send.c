/* 临时 UDP 发送工具: 从参数指定 IP/端口发 CRSF Device_Ping 帧 */
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    if (argc < 3) { fprintf(stderr, "usage: %s <ip> <port>\n", argv[0]); return 1; }
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(atoi(argv[2]));
    inet_pton(AF_INET, argv[1], &a.sin_addr);
    /* CRSF Device_Ping: [0xC8][4][0x28][0xEE][0xEA][crc] */
    unsigned char f[] = {0xC8, 0x04, 0x28, 0xEE, 0xEA, 0xA7};
    unsigned char pkt[14];
    memcpy(pkt, "RCSF", 4);
    memcpy(pkt + 4, f, sizeof(f));
    for (int i = 0; i < 5; i++) {
        sendto(fd, pkt, sizeof(pkt), 0, (struct sockaddr *)&a, sizeof(a));
        usleep(300000);
    }
    close(fd);
    printf("sent 5x %s:%s\n", argv[1], argv[2]);
    return 0;
}
