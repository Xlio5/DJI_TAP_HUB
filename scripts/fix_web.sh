#!/bin/sh
cp /usr/local/bin/web_panel.py /usr/local/bin/web_panel.py.bak4

python3 << 'PYEOF'
path = "/usr/local/bin/web_panel.py"
with open(path) as f:
    lines = f.readlines()

out = []
skip = 0
for i, line in enumerate(lines):
    if skip > 0:
        skip -= 1
        continue
    # Look for save_cfg in the config/save handler specifically
    if "elif p == \"/api/config/save\":" in line:
        # Found the handler - read the next few lines until save_cfg
        j = i + 1
        block = []
        while j < len(lines) and 'elif p == "/api/camera/add":' not in lines[j]:
            block.append(lines[j])
            j += 1
        # Rebuild: keep the handler start, then inject before save_cfg
        out.append(line)
        for bl in block:
            if 'save_cfg(cfg); self._json({"ok":True})' in bl:
                indent = "            "
                out.append(indent + 'if "lan_subnet" in body:\n')
                out.append(indent + "    try:\n")
                out.append(indent + "        import subprocess as _sp\n")
                out.append(indent + '        s = body["lan_subnet"]\n')
                out.append(indent + '        p2 = int(s.split("/")[1])\n')
                out.append(indent + '        ip = s.split("/")[0].rsplit(".", 1)[0]\n')
                out.append(indent + '        v = ip + ".66"\n')
                out.append(indent + '        _sp.run(["sed","-i",f"s/address .*/address {v}/","/etc/network/interfaces"])\n')
                out.append(indent + '        _sp.run(["ip","addr","flush","dev","eth0"])\n')
                out.append(indent + '        _sp.run(["ip","addr","add",f"{v}/{p2}","dev","eth0"])\n')
                out.append(indent + '        _sp.run(["ip","link","set","eth0","up"])\n')
                out.append(indent + '        cfg["lan_subnet"] = s\n')
                out.append(indent + "    except Exception:\n")
                out.append(indent + "        pass\n")
                out.append(bl)
            else:
                out.append(bl)
        out.append(lines[j])
        skip = j - i
    else:
        out.append(line)

with open(path, "w") as f:
    f.writelines(out)
print("OK")
PYEOF
