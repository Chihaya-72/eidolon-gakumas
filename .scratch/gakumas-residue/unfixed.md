# 闪耀色彩残留：还没修的

2026-11-05 查 `main` 时列出的残留里，这次**没有修**的部分。修掉一项就从这里删一项。

## 文档（维护者决定先不改）

- `README.md`、`README.en.md`、`README.ja.md`：还介绍闪耀色彩、283 事务所、28 位偶像，还说酒吧是现有玩法。
- `PRODUCT.md`、`GLOSSARY.md`、`DESIGN.md`：角色数、作品名、用户身份和术语还是闪耀色彩的；`GLOSSARY.md` 写着只服务闪耀色彩。
- `docs/configuration*.md`、`docs/deploy.md`：示例和同步说明针对闪耀色彩，酒吧默认值也没改成关闭。
- `docs/images/`：README 用的 15 张截图，说明文字提到闪耀色彩的角色。
- `frontend/src/app/(landing)/CREDITS.md`、`frontend/public/reset-card/CREDITS.md`：还在讲闪耀色彩的素材。

## 酒吧（已默认关闭，重开前要处理）

- 店名 `VA-283`：`BarDoor.tsx`、`zh.ts`、`bar_prompt.py` 等。
- 新手教程写死由 `hazuki` 来教（`useBarTutorial.ts`、`barTutorialLines.ts`），学园角色里没有她，所以不会触发。
- 提示词和角色包：`bar_prompt.py` 的「组合伙伴」，`characters/gakumas/bar_visits.toml` 的「组合」「事务所」。

## 暂时隐藏或不再显示，代码和文件还在

- SCSP 头像：`AppearanceSettings.tsx`、`lib/appearance.ts`、后端 `scsp_avatar` 都还在，只是设置里没有入口。
- 重置卡插画：`frontend/public/reset-card/reset-card.webp` 不再显示，但文件还在，知道地址就能打开。

## 学园角色包目前用不到，所以没改

- `today.py`、`engine.py` 的组合逻辑：`characters/gakumas/world.json` 的组合是空的，「组合伙伴的生日」这句不会出现。
- `sheet_draft.py`：生成人设初稿的命令还按事务所和组合来写。
- 同步工具：`mirror.py`、`live_sync.py`、`release_sync.py`、`setlist_sync.py`、`stand_fetch.py`、`deploy/story-sync.sh`、`deploy/stand-sync.sh` 只面向闪耀色彩的数据源。
- 角色包缺 `letter_music.toml`、`world-corrections.json`：前者缺失时读不到信的配乐，后者只给闪耀色彩的同步用。

## 留着不动

- `characters/` 下闪耀色彩的旧角色包：作为备份，默认不加载。
- `backend/tests`、`backend/eval`、前端测试：用闪耀色彩的角色当样例。
- 代码注释里的角色名、`.scratch/` 和 `docs/adr/` 的历史记录。

## 没能确认（需要在服务器上看）

- 酒吧：线上 `.env` 的 `EIDOLON_BAR`，或后台「酒吧」卡存过的设置，都会盖过新的默认值。
- 对象存储桶：可能还有闪耀色彩的立绘、来电海报和方块小人。
- 定时任务：线上如果还跑着 `deploy/story-sync.sh`、`deploy/stand-sync.sh`，可以停掉。
