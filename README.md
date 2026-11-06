<div align="center">

# Eidolon-Gakumas

**和《学园偶像大师》的角色对话的 AI 分身**

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

[![CI](https://img.shields.io/github/actions/workflow/status/Chihaya-72/eidolon-gakumas/ci.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/Chihaya-72/eidolon-gakumas/actions/workflows/ci.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-A42E2B?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

</div>

---

Eidolon-Gakumas 让你以初星学园制作人的身份，和《学园偶像大师》的 24 位角色聊天。她们会记住你说过的事，并在角色之间传开；还有好感度、礼物、日历和日程等玩法。

本项目 fork 自 [eidolon-sc](https://github.com/Sallyn0225/eidolon-sc)，角色包换成了学园偶像大师（见[角色包说明](characters/gakumas/README.md)）。

> [!NOTE]
> 目前处于测试阶段：文字对话可用；语音通话、立绘和剧情回忆还没有接入这套角色包。

> [!IMPORTANT]
> 本项目是非官方的粉丝作品，与万代南梦宫及《偶像大师》系列的版权方无关，角色由 AI 扮演。

## 快速开始

```sh
git clone https://github.com/Chihaya-72/eidolon-gakumas.git && cd eidolon-gakumas
cp .env.example .env    # 填写 CHAT_LLM_BASE_URL、CHAT_LLM_API_KEY、CHAT_LLM_MODEL，再加一行 EIDOLON_DEV_LOGIN=1
docker compose up --build
```

打开 <http://localhost:3000>，用「开发登录」进入。更多配置见 [配置指南](docs/configuration.md)、[部署指南](docs/deploy.md) 和 [`.env.example`](.env.example)。

## 许可证

代码以 [AGPL-3.0](LICENSE) 或更高版本发布，第三方素材的许可见 [`LICENSING.md`](LICENSING.md)。角色与设定的版权归原作版权方所有。

<div align="center">

<sub>《学园偶像大师》及其角色的版权归 ©Bandai Namco Entertainment Inc. 所有。本项目为非官方粉丝作品，与版权方无关。</sub>

</div>
