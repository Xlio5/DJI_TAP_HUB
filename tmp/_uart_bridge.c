/* 独立 UDP↔UART 双向透传 (验证用): 阻塞 recvfrom + 阻塞 UART read
 * UDP 65532 <-> UART0, 与 dji_rc 无关
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <pthread.h>

#define PORT 65532

/* 网口 magic: 0x46534352 little-endian = 字节 52 53 43 46 (与 App CrsfBridge + 固件 dji_rc 一致) */
static const unsigned char MAGIC[4] = {0x52, 0x53, 0x43, 0x46};

static int uart_fd = -1;
static int sock_fd = -1;

static void *uart_to_net(void *arg) {
    unsigned char buf[256];
    for (;;) {
        ssize_t n = read(uart_fd, buf, sizeof(buf));
        if (n > 0) {
            unsigned char pkt[4 + 256];
            memcpy(pkt, MAGIC, 4);
            memcpy(pkt + 4, buf, n);
            sendto(sock_fd, pkt, 4 + n, 0, (struct sockaddr *)arg, sizeof(struct sockaddr_in));
            printf("[uart→net] %ldB\n", n);
            fflush(stdout);
        }
    }
    return NULL;
}

static void set_uart(int fd, int baud) {
    struct termios t;
    memset(&t, 0, sizeof(t));
    tcgetattr(fd, &t);
    cfmakeraw(&t);
    cfsetspeed(&t, baud);
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 1;
    tcsetattr(fd, TCSANOW, &t);
}

int main(int argc, char *argv[]) {
    int baud = argc > 1 ? atoi(argv[1]) : 420000;
    // UART0 (阻塞)
    uart_fd = open("/dev/ttyS0", O_RDWR | O_NOCTTY);
    if (uart_fd < 0) { perror("open ttyS0"); return 1; }
    set_uart(uart_fd, baud);
    printf("UART0 opened fd=%d baud=%d\n", uart_fd, baud);
    fflush(stdout);

    // UDP
    sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
    int on = 1;
    setsockopt(sock_fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    struct sockaddr_in sa;
    memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_ANY);
    sa.sin_port = htons(PORT);
    if (bind(sock_fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) { perror("bind"); return 1; }
    printf("UDP %d bound\n", PORT);
    fflush(stdout);

    // UART→net (阻塞 read, 需要 peer 目标)
    struct sockaddr_in peer;
    memset(&peer, 0, sizeof(peer));
    peer.sin_family = AF_INET;
    peer.sin_port = htons(65532);
    /* UART→UDP 目标: 默认 10.0.0.2 (App), 测试时可传参覆盖为电脑 IP */
    inet_pton(AF_INET, argc > 2 ? argv[2] : "10.0.0.2", &peer.sin_addr);
    pthread_t t;
    pthread_create(&t, NULL, uart_to_net, &peer);

    // net→UART
    unsigned char buf[256];
    for (;;) {
        struct sockaddr_in from;
        socklen_t fl = sizeof(from);
        ssize_t n = recvfrom(sock_fd, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fl);
        if (n > 0) {
            if (n >= 5 && memcmp(buf, MAGIC, 4) == 0) {
                ssize_t w = write(uart_fd, buf + 4, n - 4);
                printf("[net→uart] %ldB wrote=%ld\n", n - 4, w);
            } else {
                printf("[net→uart] no-magic %ldB\n", n);
            }
            fflush(stdout);
        } else if (n < 0 && errno != EAGAIN) {
            perror("recvfrom");
        }
    }
    return 0;
}
