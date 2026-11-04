"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { WelcomeIdol } from "./idols";
import { drawArrows, layoutArrows, type Arrow } from "./arrows";
import { Chatter, type StageCopy } from "./Chatter";
import { EDGE, syncEdge } from "./edge";

/**
 * 第二页：舞台占两页的滚动距离，有两个停靠点（logo、她的话），舞台本身钉住不动。天空里先是 logo 和欢迎语；
 * 滑一次，七支印象色的箭头（每次随机挑七位）从屏幕底下往上冲，速度各不相同；跑得最快的那支——今天先来找你的
 * 那一位——冲到顶以后向两侧展开、盖满整个屏幕，她的名字出现，然后她开始一句接一句地找你（Chatter）。
 * 再滑一次就到下一页。
 *
 * 动画按时间播放，不跟手：进度 s（0..1）朝目标走，各阶段的分界在 PHASE 里。进度写成 CSS 变量（--wl-logo 等），
 * 文字和 logo 的显隐交给 welcome.css。
 */
const PHASE = {
  logoOut: [0, 0.2],
  welcomeOut: [0, 0.16],
  /** 比赛：最快的那支在这一段走完全程；之后比赛进度继续涨，别的箭头接着往上跑。 */
  race: [0, 0.6],
  pickIn: [0.55, 0.62],
  pickOut: [0.72, 0.78],
  spread: [0.6, 0.85],
  name: [0.82, 0.92],
  chatter: 0.92,
} as const;

/** 从 logo 冲到铺满、说出第一句前要多久；往回滑时收得快一些。 */
const PLAY_MS = 2400;
const REWIND_MS = 500;
/** 往下一个停靠点滚过多少就算滑了这一下：手指一动就开始，不等滚动停稳。 */
const TRIGGER = 0.12;

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
  const color = idol.color;

  useEffect(() => {
    const wrap = wrapRef.current;
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    const pager = wrap?.closest<HTMLElement>(".wl-pager");
    if (!wrap || !stage || !canvas || !pager) return;
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
      const rect = wrap.getBoundingClientRect();
      const run = rect.height - pager.clientHeight;
      return run <= 0 ? 0 : Math.min(1, Math.max(0, -rect.top / run));
    };
    const targetOf = () => (!reduced && progress() > TRIGGER ? 1 : 0);

    // 换人时（挂载后随机挑的那一位）或从后面的页滑回来时不重播，直接摆到该在的位置。
    let s = targetOf();
    let last = 0;

    const paint = () => {
      const spread = span(s, PHASE.spread);
      stage.style.setProperty("--wl-logo", String(1 - span(s, PHASE.logoOut)));
      stage.style.setProperty("--wl-welcome", String(1 - span(s, PHASE.welcomeOut)));
      stage.style.setProperty("--wl-pick", String(span(s, PHASE.pickIn) * (1 - span(s, PHASE.pickOut))));
      stage.style.setProperty("--wl-flood", String(spread));
      stage.style.setProperty("--wl-name", String(span(s, PHASE.name)));
      const [a, b] = PHASE.race;
      drawArrows(ctx, arrows, { width, height, race: (s - a) / (b - a), spread, winner });
      setChatting(s >= PHASE.chatter);
      // 铺满以后，屏幕边缘露出来的底色也换成她的颜色。
      wrap.dataset.edge = spread > 0.5 ? color : EDGE.paper;
      syncEdge(pager);
    };

    const frame = (now: number) => {
      raf = 0;
      const target = targetOf();
      const dt = last ? Math.min(100, now - last) : 0;
      if (s < target) s = Math.min(target, s + dt / PLAY_MS);
      else if (s > target) s = Math.max(target, s - dt / REWIND_MS);
      paint();
      if (s === target) {
        last = 0;
      } else {
        last = now;
        raf = requestAnimationFrame(frame);
      }
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
    pager.addEventListener("scroll", kick, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      pager.removeEventListener("scroll", kick);
    };
  }, [idols, chosen, reduced, color]);

  return (
    <div ref={wrapRef} className="wl-stage-wrap" data-edge={EDGE.paper} data-reduced={reduced || undefined}>
      {/* 两个停靠点：翻页容器停在这里。减少动态时舞台只有一页，停靠点是外层自己。 */}
      {!reduced && <span className="wl-stage-stop" aria-hidden />}
      {!reduced && <span className="wl-stage-stop" aria-hidden />}
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
