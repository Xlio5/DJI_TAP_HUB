#include "adb_client.h"

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace {

constexpr uint32_t kAdbVersion = 0x01000001;
constexpr uint32_t kMaxPayload = 256 * 1024;

bool set_nonblock(int fd, bool enabled, std::string *error)
{
    int flags = ::fcntl(fd, F_GETFL, 0);
    if (flags < 0) {
        if (error) *error = std::string("fcntl(F_GETFL): ") + std::strerror(errno);
        return false;
    }
    int next = enabled ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
    if (::fcntl(fd, F_SETFL, next) < 0) {
        if (error) *error = std::string("fcntl(F_SETFL): ") + std::strerror(errno);
        return false;
    }
    return true;
}

bool wait_fd(int fd, short events, int timeout_ms, std::string *error)
{
    pollfd pfd{};
    pfd.fd = fd;
    pfd.events = events;
    int r;
    do {
        r = ::poll(&pfd, 1, timeout_ms);
    } while (r < 0 && errno == EINTR);
    if (r == 0) {
        if (error) *error = "timeout";
        return false;
    }
    if (r < 0) {
        if (error) *error = std::string("poll: ") + std::strerror(errno);
        return false;
    }
    if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) {
        if (error) *error = "socket closed";
        return false;
    }
    return true;
}

bool write_all(int fd, const uint8_t *data, size_t len, int timeout_ms, std::string *error)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = ::send(fd, data + off, len - off, MSG_NOSIGNAL);
        if (n > 0) {
            off += (size_t)n;
            continue;
        }
        if (n < 0 && (errno == EINTR)) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            if (!wait_fd(fd, POLLOUT, timeout_ms, error)) return false;
            continue;
        }
        if (error) *error = std::string("send: ") + std::strerror(errno);
        return false;
    }
    return true;
}

bool read_all(int fd, uint8_t *data, size_t len, int timeout_ms, std::string *error)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = ::recv(fd, data + off, len - off, 0);
        if (n > 0) {
            off += (size_t)n;
            continue;
        }
        if (n == 0) {
            if (error) *error = "socket closed";
            return false;
        }
        if (errno == EINTR) continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            if (!wait_fd(fd, POLLIN, timeout_ms, error)) return false;
            continue;
        }
        if (error) *error = std::string("recv: ") + std::strerror(errno);
        return false;
    }
    return true;
}

std::string packet_name(uint32_t command)
{
    char s[5];
    s[0] = (char)(command & 0xff);
    s[1] = (char)((command >> 8) & 0xff);
    s[2] = (char)((command >> 16) & 0xff);
    s[3] = (char)((command >> 24) & 0xff);
    s[4] = '\0';
    return s;
}

}  // namespace

uint32_t adb_command(const char *cmd4)
{
    return ((uint32_t)(uint8_t)cmd4[0]) |
           ((uint32_t)(uint8_t)cmd4[1] << 8) |
           ((uint32_t)(uint8_t)cmd4[2] << 16) |
           ((uint32_t)(uint8_t)cmd4[3] << 24);
}

uint32_t adb_payload_checksum(const uint8_t *data, size_t len)
{
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            if (crc & 1u) crc = (crc >> 1) ^ 0xedb88320u;
            else crc >>= 1;
        }
    }
    return crc ^ 0xffffffffu;
}

uint32_t AdbStreamMux::allocateStream()
{
    const uint32_t local_id = next_local_id_++;
    streams_[local_id] = StreamState{};
    return local_id;
}

bool AdbStreamMux::route(const AdbPacket &packet, AdbStreamEvent *event)
{
    if (!event) return false;
    auto it = streams_.find(packet.arg1);
    if (it == streams_.end() || !it->second.open) return false;

    event->local_id = packet.arg1;
    event->remote_id = packet.arg0;
    event->data.clear();
    if (packet.command == adb_command("OKAY")) {
        it->second.remote_id = packet.arg0;
        event->type = AdbStreamEventType::Opened;
        return true;
    }
    if (packet.command == adb_command("WRTE")) {
        it->second.remote_id = packet.arg0;
        event->type = AdbStreamEventType::Data;
        if (!packet.payload.empty()) {
            event->data.assign((const char *)packet.payload.data(),
                               packet.payload.size());
        }
        return true;
    }
    if (packet.command == adb_command("CLSE")) {
        it->second.open = false;
        event->type = AdbStreamEventType::Closed;
        return true;
    }
    return false;
}

bool AdbStreamMux::isOpen(uint32_t local_id) const
{
    auto it = streams_.find(local_id);
    return it != streams_.end() && it->second.open;
}

static uint32_t adb_payload_sum(const uint8_t *data, size_t len)
{
    uint32_t sum = 0;
    for (size_t i = 0; i < len; i++) sum += data[i];
    return sum;
}

AdbClient::AdbClient() = default;

AdbClient::~AdbClient()
{
    close();
}

bool AdbClient::connect(const AdbClientOptions &options, std::string *error)
{
    close();
    fd_ = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd_ < 0) {
        if (error) *error = std::string("socket: ") + std::strerror(errno);
        return false;
    }
    io_timeout_ms_ = options.io_timeout_ms;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(options.port);
    if (::inet_aton(options.host.c_str(), &addr.sin_addr) == 0) {
        if (error) *error = "bad host: " + options.host;
        close();
        return false;
    }

    if (!set_nonblock(fd_, true, error)) {
        close();
        return false;
    }
    int r = ::connect(fd_, (sockaddr *)&addr, sizeof(addr));
    if (r < 0 && errno != EINPROGRESS) {
        if (error) *error = std::string("connect: ") + std::strerror(errno);
        close();
        return false;
    }
    if (r < 0 && !wait_fd(fd_, POLLOUT, options.connect_timeout_ms, error)) {
        close();
        return false;
    }
    int so_error = 0;
    socklen_t so_len = sizeof(so_error);
    if (::getsockopt(fd_, SOL_SOCKET, SO_ERROR, &so_error, &so_len) < 0 || so_error != 0) {
        if (error) *error = std::string("connect complete: ") +
                            std::strerror(so_error ? so_error : errno);
        close();
        return false;
    }

    const std::string banner = "host::v3s_cpp_adb";
    if (!writePacket(adb_command("CNXN"), kAdbVersion, kMaxPayload,
                     (const uint8_t *)banner.data(), banner.size(), error)) {
        close();
        return false;
    }

    AdbPacket pkt;
    if (!readPacket(&pkt, error)) {
        close();
        return false;
    }
    if (pkt.command == adb_command("AUTH")) {
        if (error) *error = "adbd requested AUTH; this small V3s client needs an already-authorized/no-auth TCP adbd";
        close();
        return false;
    }
    if (pkt.command != adb_command("CNXN")) {
        if (error) *error = "expected CNXN, got " + packet_name(pkt.command);
        close();
        return false;
    }
    return true;
}

bool AdbClient::openShell(const std::string &command, std::string *error)
{
    return openShellStream(command, &legacy_local_id_, error);
}

bool AdbClient::openShellStream(const std::string &command, uint32_t *local_id,
                                std::string *error)
{
    if (fd_ < 0) {
        if (error) *error = "not connected";
        return false;
    }
    const uint32_t id = mux_.allocateStream();
    std::string service = "shell:" + command;
    service.push_back('\0');
    if (!writePacket(adb_command("OPEN"), id, 0,
                     (const uint8_t *)service.data(), service.size(), error)) {
        return false;
    }
    if (local_id) *local_id = id;
    return true;
}

bool AdbClient::readStreamEvent(AdbStreamEvent *event, bool *timed_out,
                                std::string *error)
{
    if (timed_out) *timed_out = false;
    while (true) {
        AdbPacket packet;
        std::string read_error;
        if (!readPacket(&packet, &read_error)) {
            if (read_error == "timeout") {
                if (timed_out) *timed_out = true;
                return true;
            }
            if (error) *error = read_error;
            return false;
        }
        if (!mux_.route(packet, event)) {
            if (error) *error = "unexpected or unknown stream packet: " +
                                packet_name(packet.command);
            return false;
        }
        if (event->type == AdbStreamEventType::Data &&
            !writePacket(adb_command("OKAY"), event->local_id, event->remote_id,
                         nullptr, 0, error)) {
            return false;
        }
        return true;
    }
}

bool AdbClient::readShellChunk(std::string *out, bool *closed, std::string *error)
{
    if (out) out->clear();
    if (closed) *closed = false;
    while (true) {
        AdbStreamEvent event;
        bool timed_out = false;
        if (!readStreamEvent(&event, &timed_out, error)) return false;
        if (timed_out) return true;
        if (event.local_id != legacy_local_id_) continue;
        if (event.type == AdbStreamEventType::Opened) continue;
        if (event.type == AdbStreamEventType::Closed) {
            if (closed) *closed = true;
            return true;
        }
        if (out) *out = std::move(event.data);
        return true;
    }
}

void AdbClient::close()
{
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
    mux_ = AdbStreamMux{};
    legacy_local_id_ = 0;
}

bool AdbClient::writePacket(uint32_t command, uint32_t arg0, uint32_t arg1,
                            const uint8_t *payload, size_t len, std::string *error)
{
    uint32_t header[6];
    header[0] = command;
    header[1] = arg0;
    header[2] = arg1;
    header[3] = (uint32_t)len;
    header[4] = adb_payload_checksum(payload, len);
    header[5] = command ^ 0xffffffffu;
    if (!write_all(fd_, (const uint8_t *)header, sizeof(header), io_timeout_ms_, error)) return false;
    if (len > 0 && payload)
        return write_all(fd_, payload, len, io_timeout_ms_, error);
    return true;
}

bool AdbClient::readPacket(AdbPacket *packet, std::string *error)
{
    uint32_t header[6];
    if (!read_all(fd_, (uint8_t *)header, sizeof(header), io_timeout_ms_, error)) return false;
    uint32_t command = header[0];
    uint32_t len = header[3];
    uint32_t checksum = header[4];
    uint32_t magic = header[5];
    if ((command ^ 0xffffffffu) != magic) {
        if (error) *error = "bad packet magic";
        return false;
    }
    if (len > kMaxPayload) {
        if (error) *error = "packet too large";
        return false;
    }
    packet->command = command;
    packet->arg0 = header[1];
    packet->arg1 = header[2];
    packet->payload.assign(len, 0);
    if (len > 0 && !read_all(fd_, packet->payload.data(), len, io_timeout_ms_, error)) return false;
    uint32_t crc = adb_payload_checksum(packet->payload.data(), packet->payload.size());
    uint32_t sum = adb_payload_sum(packet->payload.data(), packet->payload.size());
    if (checksum != 0 && crc != checksum && sum != checksum) {
        if (error) {
            char buf[160];
            std::snprintf(buf, sizeof(buf),
                          "bad packet checksum cmd=%s len=%u got=0x%08x crc32=0x%08x sum=0x%08x",
                          packet_name(command).c_str(), len, checksum, crc, sum);
            *error = buf;
        }
        return false;
    }
    return true;
}
