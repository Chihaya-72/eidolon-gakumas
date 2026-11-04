"use client";

import { AlarmClock, Ellipsis, Grid3x3, MessageCircle, Mic, Phone, Video, Volume2 } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";

import { tint, shade, type WelcomeIdol } from "./idols";
import { useInView } from "./useReducedMotion";

export type CallCopy = {
  title: string;
  body: string;
  incoming: string;
  remind: string;
  message: string;
  slide: string;
  answer: string;
  speaker: string;
  facetime: string;
  mute: string;
  more: string;
  end: string;
  keypad: string;
  ended: string;
  again: string;
  hint: string;
};

type State = "ringing" | "connected" | "ended";

/** 接通以后，字幕多久换一句。 */
const LINE_MS = 3600;

/**
 * 第三页：她打来电话。一台 iPhone，屏幕是 iOS 的来电画面，按钮是液态玻璃；滑动滑块或点绿色按钮接听，
 * 接通后计时、她说话的日语原文和中文字幕一句句出现；挂断以后过一会儿她又打来。不出声。
 */
export function PhoneCall({ idol, copy, reduced }: { idol: WelcomeIdol; copy: CallCopy; reduced: boolean }) {
  const [state, setState] = useState<State>("ringing");
  const [seconds, setSeconds] = useState(0);
  const [line, setLine] = useState(0);
  const sectionRef = useRef<HTMLElement>(null);
  const phoneRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, 0.4);

  // 换了一位偶像（第一次挂载后随机挑的那一位）就从来电重新开始。
  useEffect(() => {
    setState("ringing");
  }, [idol.id]);

  useEffect(() => {
    if (state !== "connected") return;
    setSeconds(0);
    setLine(0);
    const clock = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    const talk = window.setInterval(() => setLine((l) => l + 1), LINE_MS);
    return () => {
      window.clearInterval(clock);
      window.clearInterval(talk);
    };
  }, [state]);

  useEffect(() => {
    if (state !== "ended") return;
    const again = window.setTimeout(() => setState("ringing"), 2600);
    return () => window.clearTimeout(again);
  }, [state]);

  // 电脑上指针移动时手机微微转向指针。
  const tilt = (e: ReactPointerEvent<HTMLElement>) => {
    const phone = phoneRef.current;
    if (!phone || reduced || e.pointerType !== "mouse") return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    phone.style.setProperty("--wl-tilt-x", `${(-y * 8).toFixed(2)}deg`);
    phone.style.setProperty("--wl-tilt-y", `${(x * 12).toFixed(2)}deg`);
  };

  const lines = [idol.call, ...idol.chatter];
  const current = lines[line % lines.length];
  const time = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <section
      ref={sectionRef}
      className="wl-call"
      aria-labelledby="wl-call-title"
      onPointerMove={tilt}
      style={
        {
          "--her": idol.color,
          "--her-ink": idol.ink,
          "--her-deep": idol.deep,
          "--her-soft": tint(idol.color, 0.55),
          "--her-dark": shade(idol.color, 0.62),
        } as CSSProperties
      }
    >
      <div className="wl-call-copy">
        <h2 id="wl-call-title" className="wl-title">
          {copy.title}
        </h2>
        <p className="wl-body">{copy.body}</p>
        <p className="wl-call-hint">{copy.hint}</p>
      </div>

      <div className="wl-iphone-stage">
        <div
          ref={phoneRef}
          className="wl-iphone"
          data-state={state}
          data-ring={(state === "ringing" && inView && !reduced) || undefined}
        >
          <span className="wl-iphone-btn wl-iphone-action" aria-hidden />
          <span className="wl-iphone-btn wl-iphone-vol-up" aria-hidden />
          <span className="wl-iphone-btn wl-iphone-vol-down" aria-hidden />
          <span className="wl-iphone-btn wl-iphone-power" aria-hidden />
          <span className="wl-iphone-btn wl-iphone-camera" aria-hidden />
          <div className="wl-iphone-screen">
            <div className="wl-wallpaper" aria-hidden>
              <span className="wl-wallpaper-glyph" lang="ja">
                {idol.ja.slice(-2)}
              </span>
            </div>
            <div className="wl-island" aria-hidden />
            <StatusBar />

            {state !== "connected" ? (
              <div className="wl-incoming" aria-live="polite">
                <p className="wl-incoming-label">{state === "ended" ? copy.ended : copy.incoming}</p>
                <p className="wl-incoming-name" lang="ja">
                  {idol.ja}
                </p>
                {state === "ended" && <p className="wl-incoming-again">{copy.again}</p>}
                {state === "ringing" && (
                  <div className="wl-incoming-actions">
                    <div className="wl-glass-row">
                      <span className="wl-glass wl-glass-pill">
                        <AlarmClock aria-hidden />
                        {copy.remind}
                      </span>
                      <span className="wl-glass wl-glass-pill">
                        <MessageCircle aria-hidden />
                        {copy.message}
                      </span>
                    </div>
                    <SlideToAnswer label={copy.slide} answer={copy.answer} onAnswer={() => setState("connected")} />
                  </div>
                )}
              </div>
            ) : (
              <div className="wl-incall">
                <div className="wl-incall-head">
                  <p className="wl-incall-name" lang="ja">
                    {idol.ja}
                  </p>
                  <p className="wl-incall-time">{time}</p>
                </div>
                <div className="wl-caption wl-glass" key={line} aria-live="polite">
                  <p lang="ja" className="wl-caption-ja">
                    {current.ja}
                  </p>
                  <p className="wl-caption-zh">{current.zh}</p>
                </div>
                <div className="wl-controls">
                  <CallButton label={copy.speaker} icon={<Volume2 />} />
                  <CallButton label={copy.facetime} icon={<Video />} />
                  <CallButton label={copy.mute} icon={<Mic />} />
                  <CallButton label={copy.more} icon={<Ellipsis />} />
                  <button type="button" className="wl-ctl wl-ctl-end" onClick={() => setState("ended")}>
                    <span className="wl-ctl-face">
                      <Phone aria-hidden className="wl-hangup-icon" />
                    </span>
                    <span className="wl-ctl-label">{copy.end}</span>
                  </button>
                  <CallButton label={copy.keypad} icon={<Grid3x3 />} />
                </div>
              </div>
            )}
            <span className="wl-home-bar" aria-hidden />
          </div>
        </div>
      </div>
    </section>
  );
}

function CallButton({ label, icon }: { label: string; icon: React.ReactNode }) {
  return (
    <span className="wl-ctl">
      <span className="wl-ctl-face wl-glass" aria-hidden>
        {icon}
      </span>
      <span className="wl-ctl-label">{label}</span>
    </span>
  );
}

function StatusBar() {
  return (
    <div className="wl-status" aria-hidden>
      <span className="wl-status-time">9:41</span>
      <span className="wl-status-icons">
        <svg viewBox="0 0 18 12" width="18" height="12">
          <rect x="0" y="8" width="3" height="4" rx="1" />
          <rect x="5" y="5.5" width="3" height="6.5" rx="1" />
          <rect x="10" y="3" width="3" height="9" rx="1" />
          <rect x="15" y="0" width="3" height="12" rx="1" />
        </svg>
        <svg viewBox="0 0 16 12" width="16" height="12">
          <path d="M8 2.2c2.4 0 4.6.9 6.2 2.5l1.3-1.4A10.6 10.6 0 0 0 8 .3 10.6 10.6 0 0 0 .5 3.3l1.3 1.4A8.7 8.7 0 0 1 8 2.2Zm0 3.7c1.4 0 2.7.5 3.6 1.4l1.3-1.4A7 7 0 0 0 8 4a7 7 0 0 0-4.9 1.9l1.3 1.4C5.3 6.4 6.6 5.9 8 5.9Zm0 3.6c.5 0 1 .2 1.3.5L8 11.5 6.7 10c.3-.3.8-.5 1.3-.5Z" />
        </svg>
        <span className="wl-battery">
          <span />
        </span>
      </span>
    </div>
  );
}

/** iOS 的「滑动来接听」：拖动绿色按钮到右边接听；点一下绿色按钮也能接（键盘、读屏器用）。 */
function SlideToAnswer({ label, answer, onAnswer }: { label: string; answer: string; onAnswer: () => void }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState(0);
  const drag = useRef<{ start: number; max: number } | null>(null);
  /** 这一次按下以后拖动过没有；拖动后浏览器补的 click 不算点按。 */
  const moved = useRef(false);

  const down = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const track = trackRef.current;
    if (!track) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const thumb = e.currentTarget.getBoundingClientRect().width;
    drag.current = { start: e.clientX, max: track.clientWidth - thumb - 8 };
    moved.current = false;
  };
  const move = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = Math.min(d.max, Math.max(0, e.clientX - d.start));
    if (dx > 4) moved.current = true;
    setOffset(dx);
  };
  const up = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (offset > d.max * 0.62) onAnswer();
    else setOffset(0);
  };

  return (
    <div ref={trackRef} className="wl-slide wl-glass" style={{ "--wl-slide": `${offset}px` } as CSSProperties}>
      <span className="wl-slide-label">{label}</span>
      <button
        type="button"
        className="wl-slide-thumb"
        aria-label={answer}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onClick={() => {
          // 拖动结束时浏览器也会补一个 click；只有没拖动过的点击才直接接听。
          if (!moved.current) onAnswer();
          moved.current = false;
        }}
      >
        <Phone aria-hidden />
      </button>
    </div>
  );
}
