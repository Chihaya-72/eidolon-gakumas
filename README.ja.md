<div align="center">

# Eidolon-Gakumas

**『学園アイドルマスター』のキャラクターと話せる AI 分身**

[简体中文](README.md) · [English](README.en.md) · **日本語**

[![CI](https://img.shields.io/github/actions/workflow/status/Chihaya-72/eidolon-gakumas/ci.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=CI)](https://github.com/Chihaya-72/eidolon-gakumas/actions/workflows/ci.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-A42E2B?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

</div>

---

Eidolon-Gakumas では、初星学園のプロデューサーとして『学園アイドルマスター』の 24 人のキャラクターとチャットできます。話したことを覚えていて、キャラクターの間で話が伝わります。好感度、プレゼント、カレンダー、スケジュールなどの遊びもあります。

このプロジェクトは [eidolon-sc](https://github.com/Sallyn0225/eidolon-sc) のフォークで、キャラクターパックを学園アイドルマスターに切り替えたものです（[キャラクターパックの説明](characters/gakumas/README.md)、中国語）。

> [!NOTE]
> 現在テスト中です。テキストでの会話は使えます。音声通話、立ち絵、ストーリーの回想はまだこのキャラクターパックに対応していません。

> [!IMPORTANT]
> 本プロジェクトは非公式のファン作品であり、バンダイナムコおよび『アイドルマスター』シリーズの権利者とは関係ありません。キャラクターは AI が演じています。

## クイックスタート

```sh
git clone https://github.com/Chihaya-72/eidolon-gakumas.git && cd eidolon-gakumas
cp .env.example .env    # CHAT_LLM_BASE_URL、CHAT_LLM_API_KEY、CHAT_LLM_MODEL を記入し、EIDOLON_DEV_LOGIN=1 を追加
docker compose up --build
```

<http://localhost:3000> を開き、「開発ログイン」で入ります。詳しくは [設定ガイド](docs/configuration.ja.md)、[デプロイガイド](docs/deploy.md)、[`.env.example`](.env.example) を見てください。

## ライセンス

コードは [AGPL-3.0](LICENSE) またはそれ以降のバージョンで公開しています。第三者の素材のライセンスは [`LICENSING.md`](LICENSING.md) にあります。キャラクターと設定の権利は原作の権利者に帰属します。

<div align="center">

<sub>『学園アイドルマスター』およびそのキャラクターの著作権は ©Bandai Namco Entertainment Inc. に帰属します。本プロジェクトは非公式のファン作品であり、権利者とは関係ありません。</sub>

</div>
