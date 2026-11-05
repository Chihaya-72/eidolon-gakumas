// 当前欢迎页的构建版验收：node scripts/landing-check.mjs [origin]
// 前端与后端须先启动；只检查访客页面，不登录、不写用户数据。
import assert from "node:assert/strict";

import { chromium } from "playwright";

const origin = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHROMIUM_CHANNEL || undefined });
try {
  for (const profile of [
    { name: "desktop", viewport: { width: 1440, height: 900 } },
    { name: "phone", viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true },
    { name: "small-phone", viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true },
    { name: "reduced", viewport: { width: 390, height: 844 }, reducedMotion: "reduce" },
  ]) {
    const { name, ...options } = profile;
    const context = await browser.newContext(options);
    try {
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const route of ["/", "/about"]) {
        await page.goto(`${origin}${route}`);
        await page.locator("#wl-title").waitFor();
        assert.equal(await page.locator("#wl-title").textContent(), "Eidolon-Gakumas");
        const titleFits = await page.locator("#wl-title").evaluate((title) => {
          const style = getComputedStyle(title);
          return title.clientHeight < Number.parseFloat(style.fontSize) * 1.2;
        });
        assert.ok(titleFits, `${name} ${route}: project name should fit on one line`);
        assert.equal(await page.title(), "Eidolon-Gakumas");
        assert.equal(await page.locator(".lp-root, .lp-canvas").count(), 0);
        assert.equal(await page.locator(".wl-pager > div").count(), 5);
        assert.equal(await page.locator(".wl-top a").getAttribute("href"), "https://github.com/Chihaya-72/eidolon-gakumas");
        assert.equal(await page.evaluate(() => document.documentElement.hasAttribute("data-lp-tier")), false);
        const overflowing = await page.locator(".wl-page").evaluateAll((pages) => pages.some((p) => p.scrollWidth > p.clientWidth + 1));
        assert.equal(overflowing, false, `${name} ${route}: horizontal overflow`);
        await page.locator(".wl-top button").click();
        await page.getByRole("dialog").waitFor();
        await page.keyboard.press("Escape");
        await page.getByRole("dialog").waitFor({ state: "hidden" });
        await page.locator(".wl-pager").evaluate((pager) => { pager.scrollTop = pager.scrollHeight; });
        await page.locator('.wl-footer a[href="/privacy"]').waitFor();
        assert.equal(await page.locator('.wl-footer a[href="/terms"]').count(), 1);
        assert.deepEqual(errors, [], `${name} ${route}: browser errors`);
        console.log(`✓ ${name} ${route}: name, layout, login, and legal links`);
      }
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
