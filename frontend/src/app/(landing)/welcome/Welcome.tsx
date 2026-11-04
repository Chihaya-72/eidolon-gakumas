"use client";

import { useEffect, useState, type CSSProperties } from "react";

import { LandingEntry } from "../LandingEntry";
import { Stage } from "./Stage";
import type { StageCopy } from "./Chatter";
import type { WelcomeIdol } from "./idols";
import { MemoryWeb, type MemoryCopy } from "./MemoryWeb";
import { PhoneCall, type CallCopy } from "./PhoneCall";
import { useReducedMotion } from "./useReducedMotion";

export type WelcomeCopy = {
  intro: {
    kicker: string;
    body: string;
    features: { title: string; body: string }[];
    cast: string;
    scroll: string;
  };
  stage: StageCopy;
  call: CallCopy;
  memory: MemoryCopy;
  entry: { kicker: string; title: string; body: string; notice: string; credit: string };
};

export type WelcomeProps = {
  appName: string;
  description: string;
  disclaimer: string;
  copy: WelcomeCopy;
  idols: WelcomeIdol[];
  isSignedIn: boolean;
  entryLabel: string;
  /** 入口按钮的类名（shadcn 的 buttonVariants），服务端算好：右上角的、最后一页的大按钮。 */
  entryClassName: { header: string; large: string; repo: string };
  repository: { url: string; label: string };
  /** 使用须知：登录方式等由服务端按后端的登录选项写好。 */
  notices: string[];
  legal: { disclaimer: string; privacy: string; terms: string };
  logoSrc: string;
};

/**
 * 欢迎页：五页往上滑。① 介绍；② 天空里的 logo，七支印象色的箭头往上冲，跑得最快的那位的颜色铺满屏幕、她一句接一句地找你；
 * ③ 她打来电话（iPhone，液态玻璃）；④ 她记住的事在偶像之间传开；⑤ 入口。
 *
 * 今天先来找你的是哪一位，在浏览器里随机挑（服务端和第一次渲染都是第一位，挂载后再换，避免水合不一致）。
 */
export function Welcome(props: WelcomeProps) {
  const { copy, idols } = props;
  const reduced = useReducedMotion();
  const [chosen, setChosen] = useState(0);

  useEffect(() => {
    setChosen(Math.floor(Math.random() * idols.length));
  }, [idols.length]);

  const her = idols[chosen];

  return (
    <div className="wl-root">
      <header className="wl-top">
        <a href={props.repository.url} target="_blank" rel="noopener noreferrer" className={props.entryClassName.repo}>
          {props.repository.label}
        </a>
        <LandingEntry isSignedIn={props.isSignedIn} label={props.entryLabel} className={props.entryClassName.header} />
      </header>

      <main>
        <Intro {...props} />
        <Stage idols={idols} chosen={chosen} copy={copy.stage} reduced={reduced} logoSrc={props.logoSrc} />
        <PhoneCall idol={her} copy={copy.call} reduced={reduced} />
        <MemoryWeb idols={idols} chosen={chosen} copy={copy.memory} reduced={reduced} />
        <Entry {...props} />
      </main>
    </div>
  );
}

function Intro({ appName, description, disclaimer, copy, idols }: WelcomeProps) {
  const t = copy.intro;
  return (
    <section className="wl-intro" aria-labelledby="wl-title">
      <div className="wl-intro-inner">
        <p className="wl-kicker" lang="ja">
          {t.kicker}
        </p>
        <h1 id="wl-title" className="wl-intro-title">
          {appName}
        </h1>
        <p className="wl-intro-lede">{description}</p>
        <p className="wl-intro-body">{t.body}</p>

        <ol className="wl-features">
          {t.features.map((f, i) => (
            <li key={f.title} className="wl-feature" style={{ "--c": idols[(i * 3) % idols.length].color } as CSSProperties}>
              <span className="wl-feature-index" aria-hidden>
                {String(i + 1).padStart(2, "0")}
              </span>
              <h2 className="wl-feature-title">{f.title}</h2>
              <p className="wl-feature-body">{f.body}</p>
            </li>
          ))}
        </ol>

        <div className="wl-cast">
          <p className="wl-cast-label">{t.cast}</p>
          <ul className="wl-cast-list">
            {idols.map((idol) => (
              <li key={idol.id} style={{ "--c": idol.color } as CSSProperties} lang="ja">
                <span className="wl-cast-dot" aria-hidden />
                {idol.ja}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="wl-disclaimer">{disclaimer}</p>
      <div className="wl-scroll" aria-hidden>
        <span>{t.scroll}</span>
        <span className="wl-scroll-line" />
      </div>
      <div className="wl-intro-band" aria-hidden>
        {idols.map((idol) => (
          <span key={idol.id} style={{ "--c": idol.color } as CSSProperties} />
        ))}
      </div>
    </section>
  );
}

function Entry({ copy, isSignedIn, entryLabel, entryClassName, notices, legal, logoSrc, idols }: WelcomeProps) {
  const t = copy.entry;
  return (
    <section className="wl-entry" aria-labelledby="wl-entry-title">
      <div className="wl-entry-rays" aria-hidden>
        {idols.map((idol, i) => (
          <span key={idol.id} style={{ "--c": idol.color, "--i": i } as CSSProperties} />
        ))}
      </div>
      <div className="wl-entry-inner">
        {/* eslint-disable-next-line @next/next/no-img-element -- 装饰用的小 logo。 */}
        <img className="wl-entry-logo" src={logoSrc} alt="" width={897} height={827} loading="lazy" />
        <p className="wl-kicker" lang="ja">
          {t.kicker}
        </p>
        <h2 id="wl-entry-title" className="wl-title">
          {t.title}
        </h2>
        <p className="wl-body">{t.body}</p>
        <div className="wl-entry-cta">
          <LandingEntry isSignedIn={isSignedIn} label={entryLabel} className={entryClassName.large} />
        </div>

        <div className="wl-notice">
          <h3 className="wl-notice-title">{t.notice}</h3>
          <ul>
            {notices.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
      {/* 用普通的 <a>：隐私政策、使用条款在应用的根 layout 下，跨根 layout 本来就是整页加载。 */}
      <footer className="wl-footer">
        <p>{legal.disclaimer}</p>
        <p>{t.credit}</p>
        <p className="wl-footer-links">
          <a href="/privacy">{legal.privacy}</a>
          <a href="/terms">{legal.terms}</a>
        </p>
      </footer>
    </section>
  );
}
