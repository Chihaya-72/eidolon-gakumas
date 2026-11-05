# 学园偶像大师人设

程序默认加载这套配置，24 位角色均可选择并进行文字对话。人设来源是用户提供的 `学园偶像大师人设/` 目录；`sheets/` 完整保留对应 Markdown 原文，`facts` 也指向同一份文件，避免人设和检索资料不一致。

`characters.toml` 维护角色标识、显示名、简介和人设路径；`world.json` 维护共同背景和人物身份。配角仍按各自的人设与用户相处，不会被统一设定为用户负责的偶像。原《闪耀色彩》配置保留在上级目录，当前默认不加载。

原文没有公开的生日、年龄使用 `"unknown"`；接口中的未知生日为 `null`，不会在日历创建生日。`cycles_enabled = false` 可关闭不适用角色的周期玩法；年龄未知时也不启用周期。中性界面占位色不是官方印象色。礼物、酒吧口味采用统一的玩法默认值，不是原作事实。

这批文件没有提供 Fish Audio 音色、头像、立绘或背景图，所以 `voice_id` 暂留空，图片使用界面原有的后备样式。文字对话可用；语音需在各角色配置中填入对应音色后启用。

在 `backend/` 启动时默认路径为 `../characters/gakumas/characters.toml`；Docker 镜像内默认路径为 `/characters/gakumas/characters.toml`。已有 `EIDOLON_CHARACTERS_PATH` 环境变量或命令行 `--characters` 会覆盖默认值。修改后重启后端；Docker 使用修改后的代码时需重新构建后端镜像。

后续替换人设时，按角色标识更新 `sheets/<id>.md`；新增、改名或更改首页文案后，在 `frontend/` 运行 `node scripts/landing-fonts.mts` 更新字体。此角色包的世界设定为人工整理；现有 `eidolon world sync`、`stand fetch` 和原作剧情同步命令面向《闪耀色彩》，不用于此包。
