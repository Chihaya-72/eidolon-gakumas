/**
 * 欢迎页的 13 位偶像：角色标识和印象色，按原作的登场顺序。
 * 印象色出处是アイマスDB「アイドルのイメージカラー」（数据来自官方网站）。名字和台词在文案目录
 * （copy.landing.welcome.idols），这里只放数据。
 */
export const IDOL_COLORS = [
  { id: "saki", color: "#e30f25" },
  { id: "temari", color: "#0c7bbb" },
  { id: "kotone", color: "#f8c112" },
  { id: "mao", color: "#7f1184" },
  { id: "lilja", color: "#eafdff" },
  { id: "china", color: "#f68b1f" },
  { id: "sumika", color: "#7cfc00" },
  { id: "hiro", color: "#00afcc" },
  { id: "rinami", color: "#f6adc6" },
  { id: "ume", color: "#ea533a" },
  { id: "misuzu", color: "#7a99cf" },
  { id: "sena", color: "#f6ae54" },
  { id: "tsubame", color: "#7b68ee" },
] as const;

export type IdolId = (typeof IDOL_COLORS)[number]["id"];

type Line = { ja: string; zh: string };

/** 页面要的一位偶像：数据加上文案。由服务端拼好传给客户端组件。 */
export type WelcomeIdol = {
  id: IdolId;
  color: string;
  /** 印象色上的字：浅色上用深字，深色上用白字。 */
  ink: string;
  /** 印象色压暗的一档，铺大面积背景时用，免得荧光色刺眼。 */
  deep: string;
  ja: string;
  short: string;
  call: Line;
  exam: Line;
  chatter: Line[];
};

function channels(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** WCAG 的相对亮度。 */
export function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const DARK_INK = "#17181d";
const LIGHT_INK = "#ffffff";

/** 在这个颜色上写字用深字还是白字：取对比度高的那一个。 */
export function inkOn(hex: string): string {
  const l = luminance(hex);
  const contrastWhite = 1.05 / (l + 0.05);
  const contrastDark = (l + 0.05) / (luminance(DARK_INK) + 0.05);
  return contrastDark >= contrastWhite ? DARK_INK : LIGHT_INK;
}

/** 按比例混进黑色。 */
export function shade(hex: string, amount: number): string {
  const [r, g, b] = channels(hex).map((c) => Math.round(c * (1 - amount)));
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/** 按比例混进白色。 */
export function tint(hex: string, amount: number): string {
  const [r, g, b] = channels(hex).map((c) => Math.round(c + (255 - c) * amount));
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}
