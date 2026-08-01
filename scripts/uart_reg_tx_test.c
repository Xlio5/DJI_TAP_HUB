#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define CCU_BASE 0x01c20000u
#define CCU_SIZE 0x1000u
#define APB2_REG 0x58u

#define UART_PAGE_BASE 0x01c28000u
#define UART1_OFF 0x400u
#define UART_SIZE 0x1000u
#define UART_THR 0x00u
#define UART_DLL 0x00u
#define UART_DLH 0x04u
#define UART_FCR 0x08u
#define UART_LCR 0x0cu
#define UART_LSR 0x14u
#define UART_DLF 0xc0u

static volatile uint32_t *reg32(void *base, uint32_t off) {
	return (volatile uint32_t *)((char *)base + off);
}

static void tiny_delay(void) {
	struct timespec ts = { .tv_sec = 0, .tv_nsec = 1000000 };
	nanosleep(&ts, NULL);
}

int main(int argc, char **argv) {
	const char *pattern = "AA55-REG-921600-TX-TEST-0123456789\r\n";
	int loops = argc > 1 ? atoi(argv[1]) : 30;
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		fprintf(stderr, "open /dev/mem: %s\n", strerror(errno));
		return 1;
	}

	void *ccu = mmap(NULL, CCU_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, CCU_BASE);
	void *uart_page = mmap(NULL, UART_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, UART_PAGE_BASE);
	if (ccu == MAP_FAILED || uart_page == MAP_FAILED) {
		fprintf(stderr, "mmap failed: %s\n", strerror(errno));
		return 1;
	}
	void *uart = (char *)uart_page + UART1_OFF;

	uint32_t old_apb2 = *reg32(ccu, APB2_REG);
	uint32_t old_lcr = *reg32(uart, UART_LCR);
	uint32_t old_dlf = *reg32(uart, UART_DLF);

	/* PLL_PERIPH0 / 41 ~= 14.634 MHz, DLL=1, DLF=0 gives near 921600. */
	*reg32(ccu, APB2_REG) = 0x02000028u;
	tiny_delay();
	*reg32(uart, UART_FCR) = 0x01u;
	*reg32(uart, UART_LCR) = 0x83u;
	*reg32(uart, UART_DLL) = 0x01u;
	*reg32(uart, UART_DLH) = 0x00u;
	*reg32(uart, UART_DLF) = 0x00u;
	*reg32(uart, UART_LCR) = 0x03u;
	tiny_delay();

	for (int n = 0; n < loops; n++) {
		for (const char *p = pattern; *p; p++) {
			while ((*reg32(uart, UART_LSR) & 0x20u) == 0)
				;
			*reg32(uart, UART_THR) = (uint8_t)*p;
		}
	}

	tiny_delay();
	*reg32(ccu, APB2_REG) = old_apb2;
	*reg32(uart, UART_LCR) = old_lcr;
	*reg32(uart, UART_DLF) = old_dlf;
	munmap(ccu, CCU_SIZE);
	munmap(uart_page, UART_SIZE);
	close(fd);
	return 0;
}
