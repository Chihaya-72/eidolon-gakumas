"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { WelcomeIdol } from "./idols";
import { drawArrows, layoutArrows, type Arrow } from "./arrows";
import { Chatter, type StageCopy } from "./Chatter";

/**
 * 第二页：钉住的一块舞台，滚动驱动。天空里先是 logo 和欢迎语；往上滑，七支印象色的箭头（每次随机挑七位）
 * 从屏幕底下往上冲，速度各不相同；跑得最快的那支——今天先来找你的那一位——冲到顶以后向两侧展开、
 * 盖满整个屏幕，她的名字出现，然后她开始一句接一句地找你（Chatter）。
 *
 * 进度 p（0..1）是这一段滚过的比例，各阶段的分界在 PHASE 里。进度写成 CSS 变量（--wl-logo 等），
 * 文字和 logo 的显隐交给 welcome.css。
 */
const PHASE = {
  logoIn: [0, 0.07],
  logoOut: [0.32, 0.42],
  welcomeIn: [0.03, 0.11],
  welcomeOut: [0.28, 0.36],
  /** 比赛：最快的那支在这一段走完全程；之后比赛进度继续涨，别的箭头接着往上跑。 */
  race: [0.1, 0.5],
  pickIn: [0.45, 0.5],
  pickOut: [0.58, 0.62],
  spread: [0.5, 0.66],
  name: [0.66, 0.72],
  chatter: 0.72,
} as const;

/** 每次挑几位上场。 */
const RUNNERS = 7;

const span = (p: number, [a, b]: readonly [number, number]) => Math.min(1, Math.max(0, (p - a) / (b - a)));

/** 挑上场的几位：她一定在，其余随机；顺序也打乱，她不一定在中间。返回颜色和她的下标。 */
function runners(idols: WelcomeIdol[], chosen: number): { colors: string[]; winner: number } {
  const others = idols.map((_, i) => i).filter((i) => i !== chosen);
  for (let i = others.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [others[i], others[j]] = [others[j], others[i]];
  }
  const picked = [chosen, ...others.slice(0, Math.min(RUNNERS, idols.length) - 1)];
  for (let i = picked.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [picked[i], picked[j]] = [picked[j], picked[i]];
  }
  return { colors: picked.map((i) => idols[i].color), winner: picked.indexOf(chosen) };
}

export function Stage({
  idols,
  chosen,
  copy,
  reduced,
  logoSrc,
}: {
  idols: WelcomeIdol[];
  chosen: number;
  copy: StageCopy;
  reduced: boolean;
  logoSrc: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [chatting, setChatting] = useState(false);
  const idol = idols[chosen];

  useEffect(() => {
    const wrap = wrapRef.current;
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !stage || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let raf = 0;
    const { colors, winner } = runners(idols, chosen);
    const arrows: Arrow[] = layoutArrows(colors, winner);

    const measure = () => {
      const rect = stage.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const progress = () => {
      if (reduced) return 0.2; // 不动的版本：天空里的 logo 和欢迎语，箭头还没上来。
      const rect = wrap.getBoundingClientRect();
      const run = rect.height - window.innerHeight;
      return run <= 0 ? 0 : Math.min(1, Math.max(0, -rect.top / run));
    };

    const frame = () => {
      raf = 0;
      const p = progress();
      const spread = span(p, PHASE.spread);
      stage.style.setProperty("--wl-logo", String(span(p, PHASE.logoIn) * (1 - span(p, PHASE.logoOut))));
      stage.style.setProperty("--wl-welcome", String(span(p, PHASE.welcomeIn) * (1 - span(p, PHASE.welcomeOut))));
      stage.style.setProperty("--wl-pick", String(span(p, PHASE.pickIn) * (1 - span(p, PHASE.pickOut))));
      stage.style.setProperty("--wl-flood", String(spread));
      stage.style.setProperty("--wl-name", String(span(p, PHASE.name)));
      const [a, b] = PHASE.race;
      drawArrows(ctx, arrows, {
        width,
        height,
        race: Math.max(0, (p - a) / (b - a)),
        spread,
        winner,
      });
      setChatting(p >= PHASE.chatter);
    };

    const kick = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };

    measure();
    kick();
    const ro = new ResizeObserver(() => {
      measure();
      kick();
    });
    ro.observe(stage);
    window.addEventListener("scroll", kick, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("scroll", kick);
    };
  }, [idols, chosen, reduced]);

  return (
    <div ref={wrapRef} className="wl-stage-wrap" data-reduced={reduced || undefined}>
      <section
        ref={stageRef}
        className="wl-stage"
        aria-labelledby="wl-stage-title"
        style={{ "--her": idol.color, "--her-ink": idol.ink } as CSSProperties}
      >
        <div className="wl-backdrop" aria-hidden>
          <span className="wl-rings" />
          <span className="wl-rule wl-rule-top">
            {copy.ruleTop.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </span>
          <span className="wl-rule wl-rule-bottom">
            {copy.ruleBottom.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </span>
          {idols.slice(0, 7).map((i, k) => (
            <span key={i.id} className="wl-sparkle" data-k={k} style={{ "--c": i.color } as CSSProperties} />
          ))}
        </div>
        <canvas ref={canvasRef} className="wl-arrows" aria-hidden />
        {/* eslint-disable-next-line @next/next/no-img-element -- 透明底的 logo，尺寸由样式决定。 */}
        <img className="wl-logo" src={logoSrc} alt="" width={897} height={827} />
        <div className="wl-stage-copy">
          <h2 id="wl-stage-title" className="wl-stage-welcome" lang="ja">
            {copy.welcome}
          </h2>
          <p className="wl-stage-welcome-zh">{copy.welcomeZh}</p>
        </div>
        <p className="wl-stage-pick" aria-hidden>
          {copy.today}
        </p>
        <div className="wl-her-name" aria-live="polite">
          <p lang="ja" className="wl-her-name-ja">
            {idol.ja}
          </p>
          <p className="wl-her-name-zh">{copy.today}</p>
        </div>
        <Chatter key={idol.id} idol={idol} copy={copy} active={chatting} reduced={reduced} />
      </section>
    </div>
  );
}
