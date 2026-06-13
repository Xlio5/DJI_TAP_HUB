/*
 * Minimal FunctionFS test — based on Linux kernel tools/usb/ffs-test.c
 * Write USB descriptors to ep0 using correct V2 format
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <endian.h>
#include <sys/types.h>

// From linux/usb/functionfs.h
#define FUNCTIONFS_DESCRIPTORS_MAGIC_V2 3
#define FUNCTIONFS_HAS_FS_DESC 1
#define FUNCTIONFS_HAS_HS_DESC 2

struct usb_functionfs_descs_head_v2 {
    __le32 magic;
    __le32 length;
    __le32 flags;
} __attribute__((packed));

// USB descriptors — vendor-specific bulk device
static const uint8_t device_desc[] = {
    18, 1, 0x00, 0x02,    // bLength, bDescriptorType, bcdUSB 2.0
    0xFF, 0, 0, 64,        // class=Vendor, subclass=0, protocol=0, maxPacket=64
    0x07, 0x22,             // idVendor = 0x2207 (LE)
    0x10, 0x00,             // idProduct = 0x0010 (LE)
    0x00, 0x01,             // bcdDevice 1.0
    1, 2, 3,                // iManufacturer, iProduct, iSerialNumber
    1                        // bNumConfigurations
};

// config + interface + 2 bulk endpoints
static const uint8_t fs_descs[] = {
    // Config descriptor
    9, 2, 32, 0, 1, 1, 0, 0x80, 0xFA,
    // Interface descriptor
    9, 4, 0, 0, 2, 0xFF, 0, 0, 0,
    // EP1 Bulk OUT (addr=0x01)
    7, 5, 0x01, 0x02, 0x00, 0x02, 0,
    // EP2 Bulk IN (addr=0x82)
    7, 5, 0x82, 0x02, 0x00, 0x02, 0,
};

static inline __le32 cpu_to_le32(uint32_t x) { return htole32(x); }

int main() {
    const char *ffs_path = "/dev/usb-ffs/tun_nat/ep0";

    int ep0 = open(ffs_path, O_RDWR);
    if (ep0 < 0) {
        perror("open ep0");
        return 1;
    }
    printf("ep0 fd=%d\n", ep0);

    // Build descriptor buffer with V2 header
    int desc_len = sizeof(device_desc) + sizeof(fs_descs);

    // V2 header size = 12 (struct) + 4 (fs_count, since flags includes FS)
    int flags = FUNCTIONFS_HAS_FS_DESC;  // = 1
    int num_counts = 1;  // only fs_count
    int header_len = sizeof(struct usb_functionfs_descs_head_v2) + num_counts * 4;
    // header = 12 + 4 = 16

    int total_len = header_len + desc_len;
    uint8_t *buf = (uint8_t*)malloc(total_len);
    if (!buf) { perror("malloc"); return 1; }

    // Fill header
    struct usb_functionfs_descs_head_v2 *h = (struct usb_functionfs_descs_head_v2*)buf;
    h->magic  = cpu_to_le32(FUNCTIONFS_DESCRIPTORS_MAGIC_V2);  // 3
    h->length = cpu_to_le32(total_len);
    h->flags  = cpu_to_le32(flags);

    // fs_count immediately after header
    uint32_t *fs_count = (uint32_t*)(buf + sizeof(struct usb_functionfs_descs_head_v2));
    *fs_count = cpu_to_le32(2);  // device_desc + fs_descs

    // Copy descriptors
    memcpy(buf + header_len, device_desc, sizeof(device_desc));
    memcpy(buf + header_len + sizeof(device_desc), fs_descs, sizeof(fs_descs));

    printf("Writing %d bytes (header=%d descs=%d flags=%d fs_count=2)\n",
           total_len, header_len, desc_len, flags);

    ssize_t n = write(ep0, buf, total_len);
    if (n != total_len) {
        printf("Write failed: wrote %zd/%d, errno=%d (%s)\n",
               n, total_len, errno, strerror(errno));

        // Try reading from ep0 to see if there's an event
        printf("Trying to read ep0 for events...\n");
        uint8_t evt[64];
        ssize_t r = read(ep0, evt, sizeof(evt));
        printf("Read returned: %zd\n", r);
        if (r < 0) printf("  errno=%d (%s)\n", errno, strerror(errno));

        free(buf);
        close(ep0);
        return 1;
    }

    printf("Descriptors written successfully!\n");

    // Write strings — empty (4 bytes zero)
    uint8_t zero[4] = {0, 0, 0, 0};
    n = write(ep0, zero, 4);
    printf("Strings write: %zd\n", n);

    if (n == 4) {
        printf("SUCCESS! ep1 and ep2 should now exist.\n");
        // Check for endpoints
        system("ls -la /dev/usb-ffs/tun_nat/");
    }

    free(buf);
    close(ep0);
    return 0;
}
