<div align="center">

# Eidolon-Gakumas

**AI companions for conversations with the characters of *Gakuen iDOLM@STER***

[简体中文](README.md) · **English** · [日本語](README.ja.md)

[![CI](https://img.shields.io/github/actions/workflow/status/Chihaya-72/eidolon-gakumas/ci.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/Chihaya-72/eidolon-gakumas/actions/workflows/ci.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-A42E2B?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

</div>

---

Eidolon-Gakumas lets you, as a producer at Hatsuboshi Gakuen, chat with 24 characters from *Gakuen iDOLM@STER*. They remember what you tell them, and word gets around among them; there are also affinity, gifts, a calendar and schedules.

This project is a fork of [eidolon-sc](https://github.com/Sallyn0225/eidolon-sc), with the character pack switched to Gakuen iDOLM@STER (see the [character pack notes](characters/gakumas/README.md), in Chinese).

> [!NOTE]
> Currently in testing: text chat works; voice calls, stands and story recall are not yet set up for this character pack.

> [!IMPORTANT]
> This is an unofficial fan project, not affiliated with Bandai Namco or the rights holders of *THE iDOLM@STER* series; the characters are played by AI.

## Quick start

```sh
git clone https://github.com/Chihaya-72/eidolon-gakumas.git && cd eidolon-gakumas
cp .env.example .env    # fill in CHAT_LLM_BASE_URL, CHAT_LLM_API_KEY, CHAT_LLM_MODEL, and add EIDOLON_DEV_LOGIN=1
docker compose up --build
```

Open <http://localhost:3000> and sign in with "Dev login". For more, see the [configuration guide](docs/configuration.en.md), the [deployment guide](docs/deploy.md) and [`.env.example`](.env.example).

## License

The code is released under [AGPL-3.0](LICENSE) or any later version; third-party assets are covered in [`LICENSING.md`](LICENSING.md). The characters and setting belong to their rights holders.

<div align="center">

<sub>*Gakuen iDOLM@STER* and its characters are ©Bandai Namco Entertainment Inc. This is an unofficial fan project, not affiliated with the rights holders.</sub>

</div>
