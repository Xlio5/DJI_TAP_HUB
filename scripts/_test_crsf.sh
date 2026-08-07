#!/bin/bash
cd /mnt/c/my_project/TUN_NAT_HUB
gcc -O2 -o /tmp/test_crsf tests/test_crsf.c \
    ubuntu/src/crsf.c ubuntu/src/rc_map.c ubuntu/src/rc_decode.c ubuntu/src/sbus.c 2>&1 | head -10
/tmp/test_crsf
