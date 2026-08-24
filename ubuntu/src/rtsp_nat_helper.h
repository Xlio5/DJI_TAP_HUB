#pragma once

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <string>
#include <vector>

static constexpr const char* rtspForwardTarget() {
    return "10.0.0.2";
}

static inline bool isIpv4Literal(const std::string& host) {
    if (host.empty()) return false;
    int parts = 0;
    size_t start = 0;
    while (start <= host.size()) {
        size_t end = host.find('.', start);
        std::string part = host.substr(start, end == std::string::npos ? end : end - start);
        if (part.empty() || part.size() > 3) return false;
        for (char c : part) {
            if (!std::isdigit(static_cast<unsigned char>(c))) return false;
        }
        int n = std::atoi(part.c_str());
        if (n < 0 || n > 255) return false;
        parts++;
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return parts == 4;
}

static inline std::string rtspHostFromUrl(const std::string& url) {
    const std::string prefix = "rtsp://";
    if (url.compare(0, prefix.size(), prefix) != 0) return "";

    size_t start = prefix.size();
    size_t path = url.find('/', start);
    std::string authority = url.substr(start, path == std::string::npos ? path : path - start);
    size_t at = authority.rfind('@');
    if (at != std::string::npos) authority = authority.substr(at + 1);

    size_t colon = authority.find(':');
    if (colon != std::string::npos) authority = authority.substr(0, colon);
    return authority;
}

static inline void addUniqueIpv4Host(std::vector<std::string>& hosts, const std::string& host) {
    if (!isIpv4Literal(host)) return;
    if (std::find(hosts.begin(), hosts.end(), host) == hosts.end()) hosts.push_back(host);
}
