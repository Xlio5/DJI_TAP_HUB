/* 微型 SPI Flash 刷写工具 — 擦除 + 写入 + 校验 */
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>

/* MTD ioctl — 硬编码，不依赖 mtd-utils 头文件 */
struct erase_info_user {
    unsigned int start;
    unsigned int length;
};
#define MEMGETINFO  _IOR('M', 1, struct mtd_info_user)
#define MEMERASE    _IOW('M', 2, struct erase_info_user)

struct mtd_info_user {
    unsigned char type;
    unsigned int  flags;
    unsigned int  size;
    unsigned int  erasesize;
    unsigned int  writesize;
    unsigned int  oobsize;
    unsigned long long padding;
};

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: flash_write <in_file> <mtd_dev>\n");
        fprintf(stderr, "  Example: flash_write /mnt/spi_image.bin /dev/mtd0\n");
        return 1;
    }

    const char *in_file = argv[1];
    const char *mtd_dev = argv[2];

    /* 1. 读取源文件 */
    FILE *fin = fopen(in_file, "rb");
    if (!fin) { perror("fopen input"); return 1; }
    fseek(fin, 0, SEEK_END);
    long fsize = ftell(fin);
    fseek(fin, 0, SEEK_SET);

    unsigned char *buf = malloc(fsize);
    if (!buf) { perror("malloc"); return 1; }
    fread(buf, 1, fsize, fin);
    fclose(fin);
    printf("Input: %s (%ld bytes)\n", in_file, fsize);

    /* 2. 打开 MTD 设备 */
    int fd = open(mtd_dev, O_RDWR);
    if (fd < 0) { perror("open mtd"); return 1; }

    /* 3. 获取 MTD 信息 */
    struct mtd_info_user mtd;
    if (ioctl(fd, MEMGETINFO, &mtd) < 0) { perror("MEMGETINFO"); return 1; }
    printf("MTD: %s size=%u erasesize=%u\n", mtd_dev, mtd.size, mtd.erasesize);

    if (fsize > (long)mtd.size) {
        fprintf(stderr, "ERROR: file too big (%ld > %u)\n", fsize, mtd.size);
        return 1;
    }

    /* 4. 擦除 */
    struct erase_info_user ei;
    ei.start = 0;
    ei.length = (unsigned int)((fsize + mtd.erasesize - 1) / mtd.erasesize) * mtd.erasesize;
    if (ei.length > mtd.size) ei.length = mtd.size;

    printf("Erasing %u bytes (offset 0)...\n", ei.length);
    if (ioctl(fd, MEMERASE, &ei) < 0) { perror("MEMERASE"); return 1; }
    printf("Erase OK\n");

    /* 5. 写入 */
    printf("Writing %ld bytes...\n", fsize);
    lseek(fd, 0, SEEK_SET);
    ssize_t written = write(fd, buf, fsize);
    if (written < 0) { perror("write"); return 1; }
    printf("Write OK (%zd bytes)\n", written);

    /* 6. 校验 */
    printf("Verifying...\n");
    lseek(fd, 0, SEEK_SET);
    unsigned char *verify_buf = malloc(fsize);
    ssize_t v = read(fd, verify_buf, fsize);
    if (v < 0) { perror("read verify"); return 1; }

    int mismatch = 0;
    for (long i = 0; i < fsize; i += 4096) {
        if (memcmp(buf + i, verify_buf + i, 4096) != 0) {
            printf("  MISMATCH at offset 0x%lx\n", i);
            mismatch = 1;
            break;
        }
    }
    if (!mismatch) printf("Verify OK — all %ld bytes match\n", fsize);

    free(buf);
    free(verify_buf);
    close(fd);
    return mismatch ? 1 : 0;
}
