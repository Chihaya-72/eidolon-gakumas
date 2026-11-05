"use client";

import { useEffect, useRef, useState } from "react";

import type { WelcomeIdol } from "./idols";

export type StageCopy = {
  welcome: string;
  welcomeZh: string;
  today: string;
  ruleTop: string[];
  ruleBottom: string[];
  calling: string;
  producer: string[];
  producerLast: string;
  producerName: string;
};

type Bubble = {
  key: number;
  from: "her" | "producer";
  ja?: string;
  zh: string;
  /** 前几句排成一列对话；之后的散落在整个屏幕上。 */
  scattered: boolean;
  x: number;
  y: number;
  rotate: number;
  scale: number;
};

/** 排成一列的有几句；超过以后开始散落、越来越快。 */
const COLUMN = 7;
/** 屏幕上最多留几句散落的，多了从最早的开始消失。 */
const MAX_SCATTERED = 72;
/** 说到第几句时，底下出现「她要打电话给你了」。 */
const CALL_AT = 46;

/** 第 n 句（从 0 数）之后隔多久说下一句：先慢慢说，散开以后一句比一句快。 */
export function delayAfter(n: number): number {
  if (n < COLUMN) return 720;
  return Math.max(40, 430 * 0.9 ** (n - COLUMN));
}

/** 第 n 句是谁说的：一列的时候她说两句、制作人回一句；散开以后大多是她。 */
export function speakerOf(n: number): "her" | "producer" {
  if (n < COLUMN) return n % 3 === 2 ? "producer" : "her";
  return n % 6 === 5 ? "producer" : "her";
}

/**
 * 铺满屏幕以后，她一句接一句地找你（日语原文 + 中文字幕），夹着制作人的几句回答（中文）。
 * `active` 为 false（往回滚出了这一段）时清空，重新进来从头说。减少动态时只摆出前几句，不再增多。
 */
export function Chatter({ idol, copy, active, reduced }: { idol: WelcomeIdol; copy: StageCopy; active: boolean; reduced: boolean }) {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [said, setSaid] = useState(0);
  const counters = useRef({ n: 0, her: 0, producer: 0, last: false });

  useEffect(() => {
    if (!active) {
      counters.current = { n: 0, her: 0, producer: 0, last: false };
      setBubbles([]);
      setSaid(0);
      return;
    }

    const next = (): Bubble => {
      const c = counters.current;
      const n = c.n++;
      const from = speakerOf(n);
      const scattered = n >= COLUMN;
      const place = {
        scattered,
        x: 14 + Math.random() * 72,
        y: 10 + Math.random() * 78,
        rotate: (Math.random() - 0.5) * 10,
        scale: 0.78 + Math.random() * 0.5,
      };
      if (from === "producer") {
        let zh: string;
        if (!c.last && n > CALL_AT - 10) {
          c.last = true;
          zh = copy.producerLast;
        } else {
          zh = copy.producer[c.producer++ % copy.producer.length];
        }
        return { key: n, from, zh, ...place };
      }
      const line = idol.chatter[c.her++ % idol.chatter.length];
      return { key: n, from, ja: line.ja, zh: line.zh, ...place };
    };

    if (reduced) {
      setBubbles(Array.from({ length: COLUMN - 1 }, next));
      setSaid(COLUMN - 1);
      return;
    }

    let timer = 0;
    const tick = () => {
      const bubble = next();
      setBubbles((list) => {
        const all = [...list, bubble];
        const scattered = all.filter((b) => b.scattered);
        if (scattered.length <= MAX_SCATTERED) return all;
        const drop = new Set(scattered.slice(0, scattered.length - MAX_SCATTERED).map((b) => b.key));
        return all.filter((b) => !drop.has(b.key));
      });
      setSaid(counters.current.n);
      timer = window.setTimeout(tick, delayAfter(bubble.key));
    };
    timer = window.setTimeout(tick, 250);
    return () => window.clearTimeout(timer);
  }, [active, reduced, idol, copy]);

  const column = bubbles.filter((b) => !b.scattered).slice(-COLUMN);
  const scattered = bubbles.filter((b) => b.scattered);

  return (
    <div className="wl-chatter" data-busy={said > COLUMN || undefined} aria-hidden={!active}>
      <ol className="wl-chat-column" aria-label={idol.ja}>
        {column.map((b) => (
          <li key={b.key} className="wl-bubble" data-from={b.from}>
            <BubbleText bubble={b} />
          </li>
        ))}
      </ol>
      <div className="wl-chat-scatter" aria-hidden>
        {scattered.map((b) => (
          <div
            key={b.key}
            className="wl-bubble wl-bubble-scattered"
            data-from={b.from}
            style={{
              left: `${b.x}%`,
              top: `${b.y}%`,
              transform: `translate(-50%, -50%) rotate(${b.rotate}deg) scale(${b.scale})`,
            }}
          >
            <BubbleText bubble={b} />
          </div>
        ))}
      </div>
      <p className="wl-calling" data-show={said >= CALL_AT || undefined}>
        <span className="wl-calling-dot" aria-hidden />
        {copy.calling}
      </p>
    </div>
  );
}

function BubbleText({ bubble }: { bubble: Bubble }) {
  if (bubble.from === "producer") return <span className="wl-bubble-zh">{bubble.zh}</span>;
  return (
    <>
      <span className="wl-bubble-ja" lang="ja">
        {bubble.ja}
      </span>
      <span className="wl-bubble-zh">{bubble.zh}</span>
    </>
  );
}
