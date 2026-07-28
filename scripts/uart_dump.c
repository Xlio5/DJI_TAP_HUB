/* uart_dump.c — 串口原始数据验证工具
 * 编译: arm-buildroot-linux-gnueabihf-gcc -O2 -s -static -o uart_dump uart_dump.c
 * 用法: ./uart_dump /dev/ttyS1 921600 5  # 921600波特率, 5秒后自动退出
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <time.h>

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "用法: uart_dump <设备> <波特率> [超时秒数=10]\n");
        fprintf(stderr, "示例: uart_dump /dev/ttyS1 921600 10\n");
        return 1;
    }
    const char *dev = argv[1];
    int baud = atoi(argv[2]);
    int timeout = argc > 3 ? atoi(argv[3]) : 10;

    int fd = open(dev, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        fprintf(stderr, "无法打开 %s: %s (dji_rc 在运行? 先 killall dji_rc)\n",
                dev, strerror(errno));
        return 1;
    }

    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    tcgetattr(fd, &tty);

    speed_t spd = B115200;
    switch (baud) {
        case 115200: spd = B115200; break;
        case 921600: spd = B921600; break;
        default: fprintf(stderr, "不支持的波特率: %d\n", baud); return 1;
    }
    cfsetispeed(&tty, spd);
    cfsetospeed(&tty, spd);
    tty.c_cflag |= (CLOCAL | CREAD | CS8);
    tty.c_iflag = IGNPAR;
    tty.c_oflag = 0;
    tty.c_lflag = 0;
    tty.c_cc[VMIN] = 1;
    tty.c_cc[VTIME] = 1;
    tcflush(fd, TCIOFLUSH);
    tcsetattr(fd, TCSANOW, &tty);

    printf("监听 %s @ %d baud, %d 秒超时, Ctrl+C 退出\n", dev, baud, timeout);
    printf("等待数据...\n\n");

    uint8_t buf[4096];
    uint32_t total = 0, lines = 0;
    time_t start = time(NULL);

    while (time(NULL) - start < timeout) {
        int n = read(fd, buf, sizeof(buf));
        if (n > 0) {
            total += n;
            for (int i = 0; i < n; i += 16) {
                int m = (n - i < 16) ? (n - i) : 16;
                printf("%08x  ", total - n + i);
                for (int j = 0; j < 16; j++) {
                    if (j < m) printf("%02x ", buf[i + j]);
                    else       printf("   ");
                }
                printf(" |");
                for (int j = 0; j < m; j++) {
                    uint8_t c = buf[i + j];
                    putchar((c >= 32 && c < 127) ? c : '.');
                }
                printf("|\n");
                lines++;
                if (lines > 100) { printf("... (截断, 已收 %u bytes)\n", total); close(fd); return 0; }
            }
        }
    }

    close(fd);
    printf("\n--- 结束 ---\n");
    printf("设备: %s @ %d baud\n", dev, baud);
    printf("共收到: %u bytes\n", total);
    if (total == 0 && timeout > 2)
        printf("无数据 → 检查接线/DJI RC是否已开机/串口号是否正确\n");
    return 0;
}
