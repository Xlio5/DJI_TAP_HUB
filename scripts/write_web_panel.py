"""Generate the updated web_panel.py with version + heartbeat + multi-camera."""
import os

# Read current file to get the Python logic
with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the HTML section boundaries
html_start = content.index('HTML = r"""')
html_end = content.index('"""', html_start + 12)  # find closing """

# Build new HTML - keep style same, replace config tab + add JS camera functions
new_html = content[html_start:html_end].replace(
    # Replace single RTSP input with multi-camera management
    '<h3>\U0001F4F9 RTSP 视频流配置</h3>\n'
    '        <div class="form-row">\n'
    '          <input id="rtsp-url" type="text" placeholder="rtsp://192.168.144.100:554/stream1">\n'
    '          <button class="btn btn-blue" onclick="saveRtsp()">\U0001F4BE 保存</button>\n'
    '        </div>\n'
    '        <div style="color:var(--dim);font-size:0.8em;margin-top:6px">摄像头地址。DJI RC App 上点播放时使用此 URL。<br>如果在 App 上改过，在这里改完需要重启 App。</div>',

    '<h3>\U0001F4F9 多路摄像头管理</h3>\n'
    '        <div style="color:var(--dim);font-size:0.8em;margin-bottom:6px">添加多个摄像头。App 通过 <code>/api/cameras</code> 自动获取。</div>\n'
    '        <div class="form-row">\n'
    '          <input id="cam-name" type="text" placeholder="名称" style="flex:0;width:100px">\n'
    '          <input id="cam-url" type="text" placeholder="rtsp://192.168.144.101:554/stream1">\n'
    '          <button class="btn btn-green" onclick="addCam()">＋ 添加</button>\n'
    '        </div>\n'
    '        <ul class="rules" id="cam-list"><li style="color:var(--dim)">加载中...</li></ul>'
)

# Replace the JS section - add camera list refresh and camera CRUD functions
old_js = '  document.getElementById("rtsp-url").value = cfg.rtsp_url||"";\n'
new_js = ('  // Camera list\n'
          '  document.getElementById("rtsp-url").value = cfg.rtsp_url||"";\n'
          '  let cl = "";\n'
          '  if (cfg.cameras && cfg.cameras.length>0) {\n'
          '    cfg.cameras.forEach((c,i)=>{cl+=`<li><span>${c.name}: ${c.url}</span><button class="btn btn-red btn-sm" onclick="delCam(${i})">删除</button></li>`});\n'
          '  } else {cl="<li style=\'color:var(--dim)\'>暂无摄像头，请添加</li>";}\n'
          '  document.getElementById("cam-list").innerHTML = cl;\n')

new_html = new_html.replace(old_js, new_js)

# Add camera JS functions after saveRtsp
old_save = '}\nrefresh();setInterval(refresh,2000);\n</script>'
new_save = ('}\n'
            'async function addCam(){\n'
            '  const name=document.getElementById("cam-name").value||"Camera";\n'
            '  const url=document.getElementById("cam-url").value;\n'
            '  if(!url){alert("请输入 RTSP 地址");return}\n'
            '  const r=await fetch(API+"/camera/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,url})});\n'
            '  if(r.ok){document.getElementById("cam-name").value="";document.getElementById("cam-url").value="";refresh();}else alert("添加失败");}\n'
            'async function delCam(idx){\n'
            '  const r=await fetch(API+"/camera/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({index:idx})});\n'
            '  if(r.ok) refresh();else alert("删除失败");}\n'
            'refresh();setInterval(refresh,2000);\n</script>')

new_html = new_html.replace(old_save, new_save)

# Add heartbeat section to config tab (before the closing config div)
old_config_end = '      </div>\n    </div>\n  </div>\n\n  <!-- ══════════ TAB: NETWORK'
heartbeat_html = ('    </div>\n\n'
                  '    <!-- 心跳状态 -->\n'
                  '    <div class="card" style="margin-top:16px">\n'
                  '      <h3>❤️ 链路心跳 (App ↔ RK3588)</h3>\n'
                  '      <div class="stat-grid">\n'
                  '        <div class="stat-item"><div class="stat-value" id="hb-daemon" style="font-size:1.1em">--</div><div class="stat-label">守护进程</div></div>\n'
                  '        <div class="stat-item"><div class="stat-value" id="hb-tty" style="font-size:1.1em">--</div><div class="stat-label">ttyGS0</div></div>\n'
                  '        <div class="stat-item"><div class="stat-value" id="hb-tun" style="font-size:1.1em">--</div><div class="stat-label">tun_hub</div></div>\n'
                  '        <div class="stat-item"><div class="stat-value" id="hb-time" style="font-size:0.9em">--</div><div class="stat-label">开机时间</div></div>\n'
                  '      </div>\n'
                  '    </div>\n  </div>\n\n  <!-- ══════════ TAB: NETWORK')

new_html = new_html.replace(old_config_end, heartbeat_html)

# Also update header version to use VERSION dynamically
new_html = new_html.replace("v''' + VERSION + '''", "${VERSION}")

# Rebuild the file
new_content = content[:html_start] + new_html + content[html_end:]

with open(r"c:\my_project\TUN_NAT_HUB\ubuntu\web_panel.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("web_panel.py updated OK")
print("Changes: version, heartbeat API, multi-camera UI, camera CRUD API")
