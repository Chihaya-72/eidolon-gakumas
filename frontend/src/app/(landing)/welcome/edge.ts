/**
 * 屏幕边缘露出来的底色：iPhone 的状态栏、底部工具栏和回弹时看到的是 <html> 的背景，不是当前这一页。
 * 每页用 data-edge 写明自己的颜色，这里按视口正中那一页同步给 <html>，边缘就不会露出一条别的颜色。
 */
export const EDGE = { paper: "#f6f7fb", night: "#0e1120", dawn: "#0e1120" } as const;

export function syncEdge(pager: HTMLElement) {
  const box = pager.getBoundingClientRect();
  const middle = box.top + box.height / 2;
  for (const page of pager.querySelectorAll<HTMLElement>("[data-edge]")) {
    const rect = page.getBoundingClientRect();
    if (rect.top <= middle && rect.bottom > middle) {
      if (page.dataset.edge) document.documentElement.style.backgroundColor = page.dataset.edge;
      return;
    }
  }
}
