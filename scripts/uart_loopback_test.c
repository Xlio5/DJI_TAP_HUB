#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>
#include <sys/mman.h>

#define UART1_BASE 0x01c28400u
#define UART1_PAGE_BASE 0x01c28000u
#define UART1_PAGE_OFFSET (UART1_BASE - UART1_PAGE_BASE)
#define UART_MAP_SIZE 0x400u
#define UART_MCR_OFFSET 0x10u

static int set_baud(int fd, int baud)
{
    struct termios tty;
    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd, &tty) < 0)
        return -1;

    speed_t spd = B115200;
    if (baud == 921600)
        spd = B921600;
    else if (baud != 115200)
        return -1;

    cfsetispeed(&tty, spd);
    cfsetospeed(&tty, spd);
    tty.c_cflag = CLOCAL | CREAD | CS8;
    tty.c_iflag = IGNPAR;
    tty.c_oflag = 0;
    tty.c_lflag = 0;
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 10;
    tcflush(fd, TCIOFLUSH);
    return tcsetattr(fd, TCSANOW, &tty);
}

int main(int argc, char **argv)
{
    const char *dev = argc > 1 ? argv[1] : "/dev/ttyS1";
    int baud = argc > 2 ? atoi(argv[2]) : 921600;
    const uint8_t pattern[] =
        "aaafdsaaaaaaaaaaaaaaaaadgb bhab rwrb werc wercwech ecw";
    uint8_t rx[sizeof(pattern)] = {0};

    int mem = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem < 0) {
        perror("open /dev/mem");
        return 1;
    }
    volatile uint32_t *page = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE,
                                   MAP_SHARED, mem, UART1_PAGE_BASE);
    volatile uint8_t *regs = (volatile uint8_t *)page + UART1_PAGE_OFFSET;
    if (page == MAP_FAILED) {
        perror("mmap uart1");
        return 1;
    }

    int fd = open(dev, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        perror("open tty");
        return 1;
    }
    if (set_baud(fd, baud) < 0) {
        perror("set_baud");
        return 1;
    }

    volatile uint32_t *mcr = (volatile uint32_t *)(regs + UART_MCR_OFFSET);
    uint32_t old_mcr = *mcr;
    *mcr = old_mcr | 0x10u;
    usleep(10000);

    ssize_t written = write(fd, pattern, sizeof(pattern) - 1);
    tcdrain(fd);
    usleep(100000);
    ssize_t n = read(fd, rx, sizeof(rx));

    *mcr = old_mcr;
    close(fd);
    munmap((void *)page, 0x1000);
    close(mem);

    printf("written=%zd read=%zd match=%s\n", written, n,
           (n == written && memcmp(pattern, rx, written) == 0) ? "true" : "false");
    printf("rx:");
    for (ssize_t i = 0; i < n; i++)
        printf(" %02x", rx[i]);
    printf("\n");
    return (n == written && memcmp(pattern, rx, written) == 0) ? 0 : 2;
}
