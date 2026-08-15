/* 读 ttyS0 的 baud_base (uartclk/16) - 权威内核 API
 * 用法: get_baudbase /dev/ttyS0 */
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/serial.h>

int main(int argc, char *argv[]) {
    const char *dev = argc > 1 ? argv[1] : "/dev/ttyS0";
    int fd = open(dev, O_RDWR | O_NOCTTY);
    if (fd < 0) { perror("open"); return 1; }
    struct serial_struct ss;
    if (ioctl(fd, TIOCGSERIAL, &ss) < 0) { perror("TIOCGSERIAL"); return 1; }
    printf("%s: type=%u baud_base=%u (uartclk=%u)\n",
           dev, ss.type, ss.baud_base, ss.baud_base * 16);
    close(fd);
    return 0;
}
