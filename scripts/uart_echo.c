/* uart_echo.c — 串口回环测试: 收到什么就发回什么
 * 编译: arm-buildroot-linux-gnueabihf-gcc -O2 -s -static -o uart_echo uart_echo.c
 * 用法: ./uart_echo /dev/ttyS1 921600   # 监听ttyS1, 921600波特率
 */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "用法: uart_echo <设备> <波特率>\n");
        fprintf(stderr, "示例: uart_echo /dev/ttyS1 921600\n");
        return 1;
    }

    const char *dev = argv[1];
    int baud = atoi(argv[2]);

    int fd = open(dev, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        fprintf(stderr, "无法打开 %s: %s\n", dev, strerror(errno));
        return 1;
    }

    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    tcgetattr(fd, &tty);

    speed_t spd = B115200;
    switch (baud) {
        case 115200: spd = B115200; break;
        case 500000: spd = B500000; break;
        case 921600: spd = B921600; break;
        default: fprintf(stderr, "不支持的波特率: %d\n", baud); return 1;
    }
    cfsetispeed(&tty, spd);
    cfsetospeed(&tty, spd);
    tty.c_cflag |= (CLOCAL | CREAD | CS8);
    tty.c_iflag &= ~(INLCR | ICRNL | IXON | IXOFF);  /* 禁CR/LF映射+流控, 防0x0D→0x0A */
    tty.c_iflag |= IGNPAR;                            /* 忽略校验错误 */
    tty.c_oflag = 0;
    tty.c_lflag = 0;          /* raw mode */
    tty.c_cc[VMIN]  = 1;      /* 至少读1字节才返回 */
    tty.c_cc[VTIME] = 0;      /* 无超时, 有数据立刻返回 */
    tcflush(fd, TCIOFLUSH);
    tcsetattr(fd, TCSANOW, &tty);

    printf("串口回环: %s @ %d baud, 收到数据立即回复, Ctrl+C 退出\n", dev, baud);
    printf("提示: 用PC串口助手连接到V3s的RX/TX脚, 发送任意数据\n\n");

    uint8_t buf[256];
    uint64_t total_rx = 0, total_tx = 0;

    while (1) {
        int n = read(fd, buf, sizeof(buf));
        if (n > 0) {
            total_rx += n;
            int sent = 0;
            while (sent < n) {
                int w = write(fd, buf + sent, n - sent);
                if (w < 0) break;
                sent += w;
            }
            total_tx += sent;
            printf("rx=%d tx=%d  total_rx=%llu total_tx=%llu\n",
                   n, sent,
                   (unsigned long long)total_rx,
                   (unsigned long long)total_tx);
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            fprintf(stderr, "读错误: %s\n", strerror(errno));
            break;
        }
    }

    close(fd);
    return 0;
}
