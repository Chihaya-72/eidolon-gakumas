/**
 * 第二页的箭头（画在 2D canvas 上）：七支纯色的印象色箭头，从屏幕底下分散的位置出发，往中间收拢着往上冲，
 * 箭尖最后都落在中间一段范围里；速度各不相同。跑得最快的那支冲到顶以后，箭身向两侧展开，直到盖满整个屏幕。
 * 位置全由调用方给的进度算，这里只管画一帧。
 */

export type Arrow = {
  color: string;
  /** 出发时（屏幕底下）箭身的横坐标，占画布宽度的比例。 */
  from: number;
  /** 冲到顶时箭尖的横坐标，占画布宽度的比例；都在中间一段范围里。 */
  to: number;
  /** 箭身宽度，占画布宽度的比例（竖屏时按高度的 0.8 倍算）。 */
  width: number;
  /** 速度：最快的那支是 1，冲到顶时比赛进度正好是 1。 */
  speed: number;
};

export type ArrowFrame = {
  width: number;
  height: number;
  /** 比赛进度：0 都还在屏幕下面，1 最快的那支刚好冲到顶；之后还会继续涨，别的箭头接着往上跑。 */
  race: number;
  /** 最快那支向两侧展开的程度，0 到 1，1 时盖满屏幕。 */
  spread: number;
  /** 最快那支在数组里的下标。 */
  winner: number;
};

function isPale(hex: string): boolean {
  const n = Number.parseInt(hex.slice(1), 16);
  return Math.min((n >> 16) & 255, (n >> 8) & 255, n & 255) > 215;
}

const clamp01 = (t: number) => Math.min(1, Math.max(0, t));
const ease = (t: number) => t * t * (3 - 2 * t);

/** 箭头的几何：头部宽是箭身的几倍、头部高是箭身宽的几倍、两侧倒钩往回收多少。 */
const HEAD_W = 2.2;
const HEAD_H = 1.5;
const BARB = 0.18;

/**
 * 在局部坐标里画一支箭：箭尖在原点，朝上（-y）；箭身往下一直伸到 `tail`。`shaft` 是当前箭身宽度，
 * `base` 是展开前的宽度（箭头按它的大小画），`head` 从 1 收到 0 时箭头缩回成箭身。
 */
function arrowPath(shaft: number, base: number, head: number, tail: number): Path2D {
  const p = new Path2D();
  const sw = shaft / 2;
  const hw = Math.max((base * HEAD_W) / 2, sw) * head + sw * (1 - head);
  const hh = base * HEAD_H * head;
  p.moveTo(0, 0);
  p.lineTo(hw, hh);
  p.lineTo(sw, hh * (1 - BARB));
  p.lineTo(sw, tail);
  p.lineTo(-sw, tail);
  p.lineTo(-sw, hh * (1 - BARB));
  p.lineTo(-hw, hh);
  p.closePath();
  return p;
}

function drawArrow(ctx: CanvasRenderingContext2D, a: Arrow, f: ArrowFrame, progress: number, spread: number) {
  const W = f.width;
  const H = f.height;
  const s = ease(clamp01(spread));
  // 竖屏（手机）上按高度放大一些，箭头不至于细得像牙签。
  const baseShaft = a.width * Math.max(W, H * 0.8);
  const headH = baseShaft * HEAD_H;
  // 从箭尖在屏幕底下（整支看不见）走到箭尖碰到顶边：横向从 from 收到 to。
  const dx = (a.to - a.from) * W;
  const dy = H + headH;
  const tilt = Math.atan2(dx, dy) * (1 - s);
  const tipX = a.from * W + dx * progress;
  const tipY = H + headH - dy * progress - headH * s;
  if (tipY >= H + headH) return;
  // 展开时箭身宽到能从它的位置盖住两边。
  const cover = 2 * Math.max(a.to * W, (1 - a.to) * W) + 40;
  const shaft = baseShaft + (cover - baseShaft) * s;

  ctx.save();
  ctx.translate(tipX, tipY);
  ctx.rotate(tilt);
  const tail = (H - tipY) / Math.cos(tilt) + H * 0.3;
  const path = arrowPath(shaft, baseShaft, 1 - s, tail);
  ctx.fillStyle = a.color;
  ctx.fill(path);
  // 很浅的颜色（莉莉娅的白）在纸白的底上看不出轮廓，描一道极细的边。
  if (s === 0 && isPale(a.color)) {
    ctx.strokeStyle = "rgb(28 36 72 / 0.16)";
    ctx.lineWidth = 1;
    ctx.stroke(path);
  }
  ctx.restore();
}

export function drawArrows(ctx: CanvasRenderingContext2D, arrows: Arrow[], f: ArrowFrame) {
  ctx.clearRect(0, 0, f.width, f.height);
  // 慢的先画；最快的那支最后画，压在所有箭头上面。
  arrows
    .map((a, i) => ({ a, i }))
    .filter(({ i }) => i !== f.winner)
    .sort((p, q) => p.a.speed - q.a.speed)
    .forEach(({ a }) => drawArrow(ctx, a, f, Math.max(0, f.race * a.speed), 0));
  const w = arrows[f.winner];
  if (!w) return;
  drawArrow(ctx, w, f, clamp01(f.race), f.spread);
  // 展开到底时整块铺满，不留一丝缝。
  if (f.spread >= 1) {
    ctx.fillStyle = w.color;
    ctx.fillRect(0, 0, f.width, f.height);
  }
}

/** 箭尖最后落在的范围（占画布宽度的比例）。 */
const LANDING: [number, number] = [0.3, 0.7];

/**
 * 摆好一组箭头：`colors` 里第 `winner` 个最快。出发位置在屏幕底下从左到右分开排，终点按同样的顺序落在
 * 中间那段范围里，所以箭头往里收、彼此不交叉。速度和宽度带一点随机，`random` 由调用方给（测试里可以固定）。
 */
export function layoutArrows(colors: string[], winner: number, random: () => number = Math.random): Arrow[] {
  const n = colors.length;
  const [lo, hi] = LANDING;
  return colors.map((color, i) => {
    const slot = n === 1 ? 0.5 : i / (n - 1);
    return {
      color,
      from: 0.06 + slot * 0.88 + (random() - 0.5) * 0.03,
      to: lo + slot * (hi - lo) + (random() - 0.5) * 0.02,
      width: 0.06 + random() * 0.025,
      speed: i === winner ? 1 : 0.45 + random() * 0.42,
    };
  });
}
