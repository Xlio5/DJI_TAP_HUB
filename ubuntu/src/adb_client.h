#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
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

enum class AdbStreamEventType {
    Opened,
    Data,
    Closed,
};

struct AdbStreamEvent {
    AdbStreamEventType type = AdbStreamEventType::Opened;
    uint32_t local_id = 0;
    uint32_t remote_id = 0;
    std::string data;
};

class AdbStreamMux {
public:
    uint32_t allocateStream();
    bool route(const AdbPacket &packet, AdbStreamEvent *event);
    bool isOpen(uint32_t local_id) const;

private:
    struct StreamState {
        uint32_t remote_id = 0;
        bool open = true;
    };

    uint32_t next_local_id_ = 1;
    std::unordered_map<uint32_t, StreamState> streams_;
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
    bool openShellStream(const std::string &command, uint32_t *local_id,
                         std::string *error);
    bool readStreamEvent(AdbStreamEvent *event, bool *timed_out,
                         std::string *error);
    void close();

private:
    bool writePacket(uint32_t command, uint32_t arg0, uint32_t arg1,
                     const uint8_t *payload, size_t len, std::string *error);
    bool readPacket(AdbPacket *packet, std::string *error);

    int fd_ = -1;
    int io_timeout_ms_ = 3000;
    AdbStreamMux mux_;
    uint32_t legacy_local_id_ = 0;
};
