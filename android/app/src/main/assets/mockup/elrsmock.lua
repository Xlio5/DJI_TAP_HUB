-- mockup/elrsmock.lua — 模拟 ELRS TX 模块参数（假数据，界面调试用）
--
-- elrs.lua setMock() 用法: local mock = loadScript("mockup/elrsmock.lua")
--   fields, goodBadPkt, deviceName = mock()
-- 所以本脚本必须返回一个函数, 调用后返回 (fields, goodBadPkt, deviceName)
--
-- 字段 type 用 CRSF 类型号: 0=UINT8 1=INT8 2=UINT16 3=INT16 8=FLOAT
--   9=SELECT 10=STRING 11=FOLDER 12=INFO 13=COMMAND 14=back/exit
-- parent 需为 nil 或省略 (root 层), getField 用 currentFolderId(nil) 匹配

local function makeFields()
  local fields = {
    { id=1, name="Power", type=0, value=25, min=10, max=100, step=5, unit=" W" },
    { id=2, name="Model Match", type=0, value=1, min=0, max=1, unit="" },
    { id=3, name="Mode", type=9, value=2, values={"Off", "On", "Auto"}, unit="" },
    { id=4, name="Packet Rate", type=9, value=3, values={"50Hz", "100Hz", "250Hz", "500Hz", "F1000"}, unit="" },
    { id=5, name="Band", type=9, value=0, values={"2.4G", "900M"}, unit="" },
    { id=6, name="Advanced", type=11 },
    { id=7, name="Info", type=12, value="ELRS 3.4.1" },
    { id=8, name="-- EXIT (Lua r18) --", type=14 },
  }
  return fields, "0/0   C", "ELRS TX"
end

return function()
  return makeFields()
end
