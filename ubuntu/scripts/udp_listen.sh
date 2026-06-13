#!/bin/bash
# UDP echo server on port 9999
echo "UDP listener starting on port 9999..."
timeout 15 nc -u -l -p 9999 -k 2>&1
echo "Done"
