/* 临时 UDP 接收测试: bind 65532, 收 5 个包打印 */
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    int port = argc > 1 ? atoi(argv[1]) : 65532;
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    int on = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_ANY);
    a.sin_port = htons(port);
    if (bind(fd, (struct sockaddr *)&a, sizeof(a)) < 0) {
        perror("bind"); return 1;
    }
    printf("listening %d\n", port);
    unsigned char buf[128];
    for (int i = 0; i < 5; i++) {
        struct sockaddr_in from;
        socklen_t fl = sizeof(from);
        ssize_t n = recvfrom(fd, buf, sizeof(buf), 0, (struct sockaddr *)&from, &fl);
        if (n > 0) {
            printf("recv %ldB from %s\n", n, inet_ntoa(from.sin_addr));
        } else {
            printf("recv %ld errno=%d\n", n, n < 0 ? errno : 0);
        }
    }
    close(fd);
    return 0;
}
