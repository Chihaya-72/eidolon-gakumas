"use client";

import { useEffect, type RefObject } from "react";

/** 两次滚轮事件隔多久算新的一次手势：触控板的惯性事件一个接一个，间隔比这短。 */
const GESTURE_GAP_MS = 140;

const KEYS: Record<string, 1 | -1> = { " ": 1, PageDown: 1, ArrowDown: 1, PageUp: -1, ArrowUp: -1 };

/** 这一页在这个方向上还能不能滚。舞台不算（它不是 .wl-page）。 */
function canScroll(page: Element | null | undefined, direction: 1 | -1): page is Element {
  if (!page) return false;
  return direction > 0 ? page.scrollTop + page.clientHeight < page.scrollHeight - 1 : page.scrollTop > 1;
}

/**
 * 滚轮和键盘的翻页。手指滑动靠 CSS 的 scroll-snap 就够了，但滚轮一格只滚一小段，会被吸回当前页，这里补上：
 * 页内还能滚就在页内滚；滚到头以后，新的一次手势翻一页（这次手势的惯性不算，不会一口气翻过去）。
 */
export function usePaging(pagerRef: RefObject<HTMLElement | null>, reduced: boolean) {
  useEffect(() => {
    const pager = pagerRef.current;
    if (!pager) return;
    const behavior: ScrollBehavior = reduced ? "auto" : "smooth";
    const turn = (direction: 1 | -1) => pager.scrollBy({ top: direction * pager.clientHeight, behavior });

    let lastWheel = -Infinity;
    let used = false;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return; // 捏合缩放
      if (e.timeStamp - lastWheel > GESTURE_GAP_MS) used = false;
      lastWheel = e.timeStamp;
      if (e.deltaY === 0 || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      const direction = e.deltaY > 0 ? 1 : -1;
      const page = e.target instanceof Element ? e.target.closest(".wl-page") : null;
      if (canScroll(page, direction)) {
        used = true;
        return;
      }
      e.preventDefault();
      if (used) return;
      used = true;
      turn(direction);
    };

    const onKey = (e: KeyboardEvent) => {
      const direction = KEYS[e.key];
      if (!direction || e.altKey || e.ctrlKey || e.metaKey) return;
      // 按钮、链接、输入框和接听滑块自己用这些键。
      if (e.target instanceof Element && e.target.closest("a, button, input, textarea, select, [role]")) return;
      e.preventDefault();
      const middle = pager.getBoundingClientRect().top + pager.clientHeight / 2;
      const page = [...pager.querySelectorAll(".wl-page")].find((p) => {
        const rect = p.getBoundingClientRect();
        return rect.top <= middle && rect.bottom > middle;
      });
      if (canScroll(page, direction)) page.scrollBy({ top: direction * page.clientHeight * 0.8, behavior });
      else turn(direction);
    };

    pager.addEventListener("wheel", onWheel, { passive: false });
    pager.addEventListener("keydown", onKey);
    return () => {
      pager.removeEventListener("wheel", onWheel);
      pager.removeEventListener("keydown", onKey);
    };
  }, [pagerRef, reduced]);
}
