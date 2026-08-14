"""Generate updated web_panel.py with version+heartbeat+multi-camera."""
import sys, io

# Read the source file
with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py", "rb") as f:
    source = f.read().decode("utf-8", errors="replace")

# Split at HTML definition
parts = source.split('HTML = r"""')
if len(parts) != 2:
    print("ERROR: cannot find HTML = r\"\"\"")
    sys.exit(1)

before_html = parts[0]
rest = parts[1]

# Find closing """
close_idx = rest.rfind('"""')
if close_idx < 0:
    print("ERROR: cannot find closing \"\"\"")
    sys.exit(1)

html_section = rest[:close_idx]
after_html = rest[close_idx:]

# --- Patch HTML section ---
# 1. Replace config tab single RTSP + RTSP card with multi-camera
old_config = (
    '<h3>\U0001F4F9 RTSP 视频流配置</h3>\n'
    '        <div class="form-row">\n'
    '          <input id="rtsp-url" type="text" placeholder="rtsp://192.168.144.100:554/stream1">\n'
    '          <button class="btn btn-blue" onclick="saveRtsp()">\U0001F4BE 保存</button>\n'
    '        </div>\n'
    '        <div style="color:var(--dim);font-size:0.8em;margin-top:6px">摄像头地址。DJI RC App 上点播放时使用此 URL。<br>如果在 App 上改过，在这里改完需要重启 App。</div>'
)

new_config = (
    '<h3>\U0001F4F9 多路摄像头管理</h3>\n'
    '        <div style="color:var(--dim);font-size:0.8em;margin-bottom:6px">'
    '添加多个摄像头。App 可通过 <code>/api/cameras</code> 获取列表切换源。<br>'
    'Web 面板修改后 App 自动同步。</div>\n'
    '        <div class="form-row">\n'
    '          <input id="cam-name" type="text" placeholder="名称" style="flex:0;width:100px">\n'
    '          <input id="cam-url" type="text" placeholder="rtsp://192.168.144.101:554/stream1">\n'
    '          <button class="btn btn-green" onclick="addCam()">＋ 添加</button>\n'
    '        </div>\n'
    '        <ul class="rules" id="cam-list"><li style="color:var(--dim)">加载中...</li></ul>'
)

html_section = html_section.replace(old_config, new_config)

# 2. Add heartbeat block after port-forward card in config tab
old_fwd_end = (
    '        <div class="warn" style="margin-top:10px">⚠️ 配了转发后，DJI RC App 里也要监听对应端口才能收到数据。</div>\n'
    '      </div>\n    </div>\n  </div>\n\n  <!-- ══════════ TAB: NETWORK'
)

new_fwd_end = (
    '        <div class="warn" style="margin-top:10px">⚠️ 配了转发后，DJI RC App 里也要监听对应端口才能收到数据。</div>\n'
    '      </div>\n'
    '    </div>\n\n'
    '    <!-- 心跳状态 -->\n'
    '    <div class="card" style="margin-top:16px">\n'
    '      <h3>❤️ 链路心跳 (App ↔ RK3588)</h3>\n'
    '      <div class="stat-grid">\n'
    '        <div class="stat-item"><div class="stat-value" id="hb-daemon" style="font-size:1.1em">--</div><div class="stat-label">守护进程</div></div>\n'
    '        <div class="stat-item"><div class="stat-value" id="hb-tty" style="font-size:1.1em">--</div><div class="stat-label">ttyGS0</div></div>\n'
    '        <div class="stat-item"><div class="stat-value" id="hb-tun" style="font-size:1.1em">--</div><div class="stat-label">tun_hub</div></div>\n'
    '        <div class="stat-item"><div class="stat-value" id="hb-time" style="font-size:0.9em">--</div><div class="stat-label">开机时间</div></div>\n'
    '      </div>\n'
    '    </div>\n'
    '  </div>\n\n  <!-- ══════════ TAB: NETWORK'
)

html_section = html_section.replace(old_fwd_end, new_fwd_end)

# 3. Update JS - add camera refresh + camera functions
old_cfg_refresh = '  document.getElementById("rtsp-url").value = cfg.rtsp_url||"";\n'
new_cfg_refresh = (
    '  document.getElementById("rtsp-url").value = cfg.rtsp_url||"";\n'
    '  // Camera list\n'
    '  let cl = "";\n'
    '  if (cfg.cameras && cfg.cameras.length>0) {\n'
    '    cfg.cameras.forEach((c,i)=>{cl+=`<li><span>${c.name}: ${c.url}</span><button class="btn btn-red btn-sm" onclick="delCam(${i})">删除</button></li>`});\n'
    '  } else {cl="<li style=\'color:var(--dim)\'>暂无摄像头，请添加</li>";}\n'
    '  document.getElementById("cam-list").innerHTML = cl;\n'
)

html_section = html_section.replace(old_cfg_refresh, new_cfg_refresh)

# 4. Add camera JS functions
old_js_end = 'refresh();setInterval(refresh,2000);\n</script>'
new_js_end = (
    'async function addCam(){\n'
    '  const name=document.getElementById("cam-name").value||"Camera";\n'
    '  const url=document.getElementById("cam-url").value;\n'
    '  if(!url){alert("请输入 RTSP 地址");return}\n'
    '  const r=await fetch(API+"/camera/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,url})});\n'
    '  if(r.ok){document.getElementById("cam-name").value="";document.getElementById("cam-url").value="";refresh();}else alert("添加失败");}\n'
    'async function delCam(idx){\n'
    '  const r=await fetch(API+"/camera/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({index:idx})});\n'
    '  if(r.ok) refresh();else alert("删除失败");}\n'
    'refresh();setInterval(refresh,2000);\n</script>'
)

html_section = html_section.replace(old_js_end, new_js_end)

# 5. Add heartbeat polling to JS refresh
old_refresh_start = 'async function refresh() {\n'
new_refresh_start = (
    'async function fetchHb(){\n'
    '  try{const r=await fetch(API+"/heartbeat");const h=await r.json();\n'
    '  document.getElementById("hb-daemon").innerHTML=h.daemon?"✅ 运行":"❌ 停止";\n'
    '  document.getElementById("hb-daemon").style.color=h.daemon?"var(--green)":"var(--red)";\n'
    '  document.getElementById("hb-tty").innerHTML=h.tty_ready?"✅ 就绪":"❌ 未检测";\n'
    '  document.getElementById("hb-tty").style.color=h.tty_ready?"var(--green)":"var(--red)";\n'
    '  document.getElementById("hb-tun").innerHTML=h.tun_up?"✅ UP":"❌ DOWN";\n'
    '  document.getElementById("hb-tun").style.color=h.tun_up?"var(--green)":"var(--red)";\n'
    '  document.getElementById("hb-time").innerHTML=h.uptime_since||"--";\n'
    '  }catch(e){}\n}\n'
    'async function refresh() {\n'
)

html_section = html_section.replace(old_refresh_start, new_refresh_start)

# Add fetchHb() call in refresh interval
html_section = html_section.replace(
    'refresh();setInterval(refresh,2000);\n',
    'fetchHb();refresh();setInterval(refresh,2000);setInterval(fetchHb,5000);\n'
)

# --- Reassemble ---
new_source = before_html + 'HTML = r"""' + html_section + after_html

with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py", "wb") as f:
    f.write(new_source.encode("utf-8"))

print("web_panel.py regenerated OK")
