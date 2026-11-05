// 从当前欢迎页生成分享预览图，避免图上的项目名与页面分开维护。
// 在前端启动后运行：node scripts/landing-og.mjs [origin]
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const origin = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const out = fileURLToPath(new URL("../src/app/(landing)/opengraph-image.jpg", import.meta.url));
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHROMIUM_CHANNEL || undefined });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
  await page.goto(`${origin}/`);
  await page.locator("#wl-title").waitFor();
  await page.evaluate(() => document.fonts.ready);
  // 预览图只展示介绍：沿用当前页面的背景、字体和文案，收起交互控件。
  await page.addStyleTag({ content: `
    .wl-top, .wl-scroll, .wl-features, .wl-cast { display: none; }
    .wl-intro { height: 630px; min-height: 630px; padding: 64px; }
    .wl-intro-title { font-size: 96px; }
    .wl-intro-body { max-width: 46em; }
    .wl-disclaimer { left: 64px; bottom: 48px; }
  ` });
  await page.screenshot({ path: out, type: "jpeg", quality: 88 });
  console.log(`写好了 ${path.relative(process.cwd(), out)}`);
} finally {
  await browser.close();
}
