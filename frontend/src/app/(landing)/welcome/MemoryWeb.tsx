"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import type { WelcomeIdol } from "./idols";
import { useInView } from "./useReducedMotion";

export type MemoryCopy = {
  title: string;
  body: string;
  producer: string;
  note: string;
  remembered: string;
  heard: string;
  heardAll: string;
  replay: string;
  producerName: string;
};

/** 画布的坐标：600×600，13 位排成一圈。 */
const SIZE = 600;
const CENTER = SIZE / 2;
const RADIUS = 238;

function nodeAt(i: number, count: number) {
  const a = -Math.PI / 2 + (i / count) * Math.PI * 2;
  // 取两位小数：服务端和浏览器算三角函数的末几位可能不同，不取整会水合不一致。
  const round = (n: number) => Math.round(n * 100) / 100;
  return { x: round(CENTER + Math.cos(a) * RADIUS), y: round(CENTER + Math.sin(a) * RADIUS) };
}

/** 从她传到别人的顺序：沿着圈，离她近的先听说。 */
export function rippleOrder(source: number, count: number): number[] {
  return Array.from({ length: count }, (_, i) => i)
    .filter((i) => i !== source)
    .sort((a, b) => ring(a, source, count) - ring(b, source, count) || a - b);
}

function ring(a: number, b: number, count: number) {
  const d = Math.abs(a - b) % count;
  return Math.min(d, count - d);
}

/**
 * 第四页：你对一位偶像说了一件事（下周要考试），她回一句、记住了，然后这件事沿着圈传给别的偶像，
 * 每一位亮起她的颜色，下面写着是听谁说的。进入视口时播放一次，可以重放；减少动态时直接摆出结果。
 */
export function MemoryWeb({ idols, chosen, copy, reduced }: { idols: WelcomeIdol[]; chosen: number; copy: MemoryCopy; reduced: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, 0.45);
  // step：0 什么都没有；1 制作人说话；2 她回话；3 她记住了；之后每多 1，多一位听说。
  const [step, setStep] = useState(0);
  // 第几次播放：0 还没进过视口；第一次进入视口时变成 1，点「再来一次」再加 1。
  const [run, setRun] = useState(0);
  const order = rippleOrder(chosen, idols.length);
  const last = 3 + order.length;
  const her = idols[chosen];

  useEffect(() => {
    if (inView) setRun((r) => (r === 0 ? 1 : r));
  }, [inView]);

  useEffect(() => {
    if (reduced) {
      setStep(last);
      return;
    }
    if (run === 0) return;
    setStep(0);
    const timers: number[] = [];
    const at = (ms: number, s: number) => timers.push(window.setTimeout(() => setStep(s), ms));
    at(250, 1);
    at(1150, 2);
    at(2300, 3);
    for (let k = 0; k < last - 3; k++) at(3000 + k * 230, 4 + k);
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [reduced, run, chosen, last]);

  const heardFrom = copy.heard.replace("{name}", her.short);
  const lit = new Map<number, number>(order.map((idx, k) => [idx, k]));
  const source = nodeAt(chosen, idols.length);

  return (
    <section ref={ref} className="wl-memory" aria-labelledby="wl-memory-title">
      <div className="wl-memory-copy">
        <h2 id="wl-memory-title" className="wl-title">
          {copy.title}
        </h2>
        <p className="wl-body">{copy.body}</p>
        {!reduced && (
          <button type="button" className="wl-replay" onClick={() => setRun((r) => r + 1)} disabled={step < last}>
            <RotateCcw aria-hidden />
            {copy.replay}
          </button>
        )}
      </div>

      <div className="wl-web-area">
        <div className="wl-web-talk">
          <p className="wl-mem-bubble" data-from="producer" data-on={step >= 1 || undefined}>
            <span className="wl-mem-who">{copy.producerName}</span>
            {copy.producer}
          </p>
          <p
            className="wl-mem-bubble"
            data-from="her"
            data-on={step >= 2 || undefined}
            style={{ "--c": her.color, "--c-ink": her.ink } as CSSProperties}
          >
            <span className="wl-mem-who" lang="ja">
              {her.ja}
            </span>
            <span lang="ja" className="wl-mem-ja">
              {her.exam.ja}
            </span>
            <span className="wl-mem-zh">{her.exam.zh}</span>
          </p>
        </div>
        <div className="wl-web" data-step={step}>
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="wl-web-lines" aria-hidden>
            <circle cx={CENTER} cy={CENTER} r={RADIUS} className="wl-web-ring" />
            <line
              x1={CENTER}
              y1={CENTER}
              x2={source.x}
              y2={source.y}
              className="wl-web-line"
              data-on={step >= 2 || undefined}
              style={{ "--c": her.color } as CSSProperties}
            />
            {order.map((idx, k) => {
              const to = nodeAt(idx, idols.length);
              const cx = Math.round(CENTER * 0.55 + ((source.x + to.x) / 2) * 0.45);
              const cy = Math.round(CENTER * 0.55 + ((source.y + to.y) / 2) * 0.45);
              return (
                <path
                  key={idx}
                  d={`M${source.x},${source.y} Q${cx},${cy} ${to.x},${to.y}`}
                  pathLength={1}
                  className="wl-web-line"
                  data-on={step >= 4 + k || undefined}
                  style={{ "--c": her.color } as CSSProperties}
                />
              );
            })}
          </svg>

          {idols.map((idol, i) => {
            const at = nodeAt(i, idols.length);
            const isHer = i === chosen;
            const on = isHer ? step >= 3 : step >= 4 + (lit.get(i) ?? 99);
            return (
              <div
                key={idol.id}
                className="wl-node"
                data-on={on || undefined}
                data-her={isHer || undefined}
                style={
                  {
                    left: `${((at.x / SIZE) * 100).toFixed(3)}%`,
                    top: `${((at.y / SIZE) * 100).toFixed(3)}%`,
                    "--c": idol.color,
                    "--c-ink": idol.ink,
                  } as CSSProperties
                }
              >
                <span className="wl-node-dot" aria-hidden />
                <span className="wl-node-name" lang="ja">
                  {idol.ja}
                </span>
                <span className="wl-node-heard">{isHer ? copy.remembered : heardFrom}</span>
              </div>
            );
          })}

          <p className="wl-mem-note" data-on={step >= 3 || undefined} style={{ "--c": her.color } as CSSProperties}>
            {copy.note}
          </p>
        </div>
        <p className="wl-web-caption" data-on={step >= last || undefined}>
          {copy.heardAll.replace("{count}", String(order.length)).replace("{name}", her.short)}
        </p>
      </div>
    </section>
  );
}
