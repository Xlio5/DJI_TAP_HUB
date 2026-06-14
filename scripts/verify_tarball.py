"""Verify tarball contents."""
import tarfile

tar_path = r"c:\my_project\TUN_NAT_HUB\tun_nat_hub_rk3588.tar.gz"
with tarfile.open(tar_path, "r:gz") as tar:
    for member in tar.getmembers():
        print("{:>8}  {}".format(member.size, member.name))

    # Check install.sh for CRLF
    f = tar.extractfile("tun_nat_hub_pkg/install.sh")
    data = f.read()
    first_line = data.split(b"\n")[0]
    has_cr = b"\r" in data
    print("\ninstall.sh: {} bytes, CR={}, first_line={}".format(len(data), has_cr, first_line[:40]))
