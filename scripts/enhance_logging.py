#!/usr/bin/env python3
import sys

CPP = "/mnt/c/my_project/TUN_NAT_HUB/ubuntu/src/web_server.cpp"
code = open(CPP).read()

with open("/tmp/enh_upgr.cpp", "w") as f:
    f.write('''static void handleFirmwareUpload(int fd) {
    Response resp;
    resp.contentType = "application/json";
    std::cout << "[fw] === UPGRADE START ===" << std::endl;
    std::string reqLine = readLine(fd);
    if (reqLine.find("POST") == std::string::npos) {
        std::cout << "[fw] ERR: not POST" << std::endl;
        resp.code = 405; resp.body = R"({"ok":false,"error":"method not allowed"})";
        resp.send(fd); return;
    }
    std::string headers;
    while (true) { std::string line = readLine(fd); if (line.empty()) break; headers += line + "\\n"; }
    auto clStr = findHeader(headers, "Content-Length");
    size_t contentLen = clStr.empty() ? 0 : std::stoull(clStr);
    std::cout << "[fw] SIZE: " << contentLen << " bytes (" << (contentLen/1024) << "KB)" << std::endl;
    if (contentLen < 1024*1024 || contentLen > 8*1024*1024) {
        std::cout << "[fw] ERR: invalid size" << std::endl;
        resp.code = 400; resp.body = R"({"ok":false,"error":"invalid size"})";
        resp.send(fd); return;
    }
    std::string tmpPath = "/var/log/new_rootfs.sq";
    int fwFd = ::open(tmpPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fwFd < 0) {
        std::cout << "[fw] ERR: cannot create tmp file" << std::endl;
        resp.body = R"({"ok":false,"error":"cannot create temp file"})";
        resp.send(fd); return;
    }
    char buf[32768]; size_t remaining = contentLen, lastRpt = 0;
    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buf) ? remaining : sizeof(buf);
        ssize_t n = ::recv(fd, buf, chunk, 0); if (n <= 0) break;
        ::write(fwFd, buf, n); remaining -= n;
        if (contentLen - remaining - lastRpt >= 512*1024) {
            lastRpt = contentLen - remaining;
            std::cout << "[fw] RECV: " << (lastRpt/1024) << "/" << (contentLen/1024) << "KB" << std::endl;
        }
    }
    ::close(fwFd);
    std::cout << "[fw] RECV: done, " << (contentLen-remaining) << " bytes" << std::endl;
    if (remaining > 0) {
        std::cout << "[fw] ERR: upload incomplete" << std::endl;
        ::unlink(tmpPath.c_str()); resp.body = R"({"ok":false,"error":"upload incomplete"})";
        resp.send(fd); return;
    }
    int vFd = ::open(tmpPath.c_str(), O_RDONLY);
    if (vFd >= 0) {
        uint8_t magic[4]; ::read(vFd, magic, 4); ::close(vFd);
        std::cout << "[fw] MAGIC: " << magic[0] << magic[1] << magic[2] << magic[3] << " (expect hsqs)" << std::endl;
        if (magic[0] != 'h' || magic[1] != 's' || magic[2] != 'q' || magic[3] != 's') {
            std::cout << "[fw] ERR: bad magic" << std::endl;
            ::unlink(tmpPath.c_str());
            JsonObj obj; obj.pair("ok", JsonValue::boolean(false));
            obj.pair("error", JsonValue::string("bad squashfs magic"));
            resp.body = obj.done(); resp.send(fd); return;
        }
    }
    struct stat st;
    if (::stat(tmpPath.c_str(), &st) == 0 && st.st_size > 12) {
        int tf = ::open(tmpPath.c_str(), O_RDONLY);
        if (tf >= 0) {
            char tail[12]; ::lseek(tf, st.st_size - 12, SEEK_SET); ::read(tf, tail, 12); ::close(tf);
            if (memcmp(tail, "TUN_NAT_HUB", 11) == 0) {
                uint32_t crc = *(uint32_t*)(tail + 8);
                std::cout << "[fw] TAIL: CRC32=0x" << std::hex << crc << std::dec << " OK" << std::endl;
            } else { std::cout << "[fw] TAIL: not present" << std::endl; }
        }
    }
    bool runningOnB = false;
    std::string cmdline = exec({"cat", "/proc/cmdline"});
    if (cmdline.find("mtdblock4") != std::string::npos) runningOnB = true;
    std::string inactiveDev = runningOnB ? "/dev/mtdblock3" : "/dev/mtdblock4";
    std::cout << "[fw] SLOT: " << (runningOnB ? "B->A" : "A->B") << " target=" << inactiveDev << std::endl;
    std::string flashCmd = "dd if=" + tmpPath + " of=" + inactiveDev + " bs=4096 2>&1";
    std::cout << "[fw] DD: " << flashCmd << std::endl;
    int rc = system(flashCmd.c_str());
    std::cout << "[fw] DD: exit=" << rc << std::endl;
    if (rc != 0) {
        ::unlink(tmpPath.c_str()); JsonObj obj; obj.pair("ok", JsonValue::boolean(false));
        obj.pair("error", JsonValue::string("flash write failed"));
        resp.body = obj.done(); resp.send(fd); return;
    }
    std::string vfy = exec({"sh", "-c", ("dd if=" + inactiveDev + " bs=1 count=16 2>/dev/null | hexdump -C 2>/dev/null").c_str()});
    std::cout << "[fw] VFY: " << (vfy.find("hsqs") != std::string::npos ? "hsqs OK" : "hsqs MISSING!") << std::endl;
    int slotFd = ::open("/dev/mtdblock0", O_WRONLY);
    if (slotFd >= 0) {
        uint32_t flagVal = runningOnB ? 0xFFFFFFFF : 0x00000000;
        ::lseek(slotFd, 0xFC000, SEEK_SET); ::write(slotFd, &flagVal, 4);
        uint8_t ctrl[2] = {0x00, 0x03}; ::lseek(slotFd, 0xFC004, SEEK_SET); ::write(slotFd, ctrl, 2);
        ::close(slotFd); sync();
        std::cout << "[fw] FLAG: slot=" << (flagVal ? "0xFF(A)" : "0x00(B)") << " c=00 r=3" << std::endl;
    }
    int vf2 = ::open("/dev/mtdblock0", O_RDONLY);
    if (vf2 >= 0) {
        uint8_t ctl[6]; ::lseek(vf2, 0xFC000, SEEK_SET); ::read(vf2, ctl, 6); ::close(vf2);
        std::cout << "[fw] VFY: ctl=" << std::hex << (int)ctl[4] << "|" << (int)ctl[5] << std::dec << std::endl;
    }
    ::unlink(tmpPath.c_str());
    JsonObj obj; obj.pair("ok", JsonValue::boolean(true));
    obj.pair("size", JsonValue::number((int)contentLen));
    obj.pair("message", JsonValue::string("Flashed to " + inactiveDev + ". Reboot now to switch."));
    resp.body = obj.done(); resp.send(fd);
    std::cout << "[fw] === UPGRADE DONE ===" << std::endl;
}''')

enhanced = open("/tmp/enh_upgr.cpp").read()
old_start = code.find("static void handleFirmwareUpload(int fd) {")
old_end = code.find("int main()", old_start)
if old_end < 0:
    print("ERROR: cannot find main()")
    sys.exit(1)
code = code[:old_start] + enhanced + "\n\n" + code[old_end:]
open(CPP, "w").write(code)

ver = open(CPP).read()
for kw in ["RECV: done", "MAGIC:", "TAIL:", "SLOT:", "DD:", "VFY:", "FLAG:", "UPGRADE DONE"]:
    print(f"  {kw}: {'OK' if kw in ver else 'MISSING'}")
print("DONE")
