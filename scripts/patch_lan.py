"""
Patch web_panel.py /api/config/save handler
Insert lan_subnet handling before save_cfg on the config/save route
"""
import subprocess as sp

path = "/usr/local/bin/web_panel.py"
sp.run(["cp", path, path + ".bak3"])

with open(path) as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    # Detect: save_cfg in config/save handler (not camera/add or camera/del)
    if 'save_cfg(cfg); self._json({"ok":True})' in line:
        next_line = lines[i+1] if i+1 < len(lines) else ""
        if 'elif p =="/api/camera/add"' in next_line.replace(' ','').replace("'",'"') or \
           'elif p == "/api/camera/add"' in next_line:
            # Found the right save_cfg — insert lan_subnet block before it
            out.pop()  # remove save_cfg we just added
            out.append('            if "lan_subnet" in body:\n')
            out.append('                try:\n')
            out.append('                    import subprocess\n')
            out.append('                    s = body["lan_subnet"]\n')
            out.append('                    p2 = int(s.split("/")[1])\n')
            out.append('                    ip = s.split("/")[0].rsplit(".", 1)[0]\n')
            out.append('                    v = ip + ".66"\n')
            out.append('                    subprocess.run(["sed","-i",f"s/address .*/address {v}/","/etc/network/interfaces"])\n')
            out.append('                    subprocess.run(["ip","addr","flush","dev","eth0"])\n')
            out.append('                    subprocess.run(["ip","addr","add",f"{v}/{p2}","dev","eth0"])\n')
            out.append('                    subprocess.run(["ip","link","set","eth0","up"])\n')
            out.append('                    cfg["lan_subnet"] = s\n')
            out.append('                except Exception:\n')
            out.append('                    pass\n')
            out.append('            save_cfg(cfg); self._json({"ok":True})\n')
    i += 1

with open(path, "w") as f:
    f.writelines(out)
print("OK")
