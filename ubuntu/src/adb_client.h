#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

uint32_t adb_command(const char *cmd4);
uint32_t adb_payload_checksum(const uint8_t *data, size_t len);

struct AdbPacket {
    uint32_t command = 0;
    uint32_t arg0 = 0;
    uint32_t arg1 = 0;
    std::vector<uint8_t> payload;
};

struct AdbClientOptions {
    std::string host = "10.0.0.2";
    uint16_t port = 5555;
    int connect_timeout_ms = 3000;
    int io_timeout_ms = 3000;
};

class AdbClient {
public:
    AdbClient();
    ~AdbClient();

    AdbClient(const AdbClient &) = delete;
    AdbClient &operator=(const AdbClient &) = delete;

    bool connect(const AdbClientOptions &options, std::string *error);
    bool openShell(const std::string &command, std::string *error);
    bool readShellChunk(std::string *out, bool *closed, std::string *error);
    void close();

private:
    bool writePacket(uint32_t command, uint32_t arg0, uint32_t arg1,
                     const uint8_t *payload, size_t len, std::string *error);
    bool readPacket(AdbPacket *packet, std::string *error);

    int fd_ = -1;
    int io_timeout_ms_ = 3000;
    uint32_t local_id_ = 1;
    uint32_t remote_id_ = 0;
};
