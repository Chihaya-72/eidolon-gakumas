// Gives every page the site's Content-Security-Policy as it is served. It is set here rather
// than in next.config, which is fixed when the image is built: where the stands are kept is
// only known where it runs. Pages rendered ahead of time stay so.
// Old and unknown settings addresses (`/settings?tab=…`, `/memories`, `/settings/<xxx>`) and the
// old gifts page, the old tasks subpage and unknown play addresses (`/gifts`, `/play/tasks`,
// `/play/<xxx>`) are redirected here to the new paths, before any page loads; a redirect leaves
// no entry in the history, so going back does not land on the old address again.

import { NextResponse, type NextRequest } from "next/server";
import { needsAccessCheck } from "@/lib/access";
import { contentSecurityPolicy } from "@/lib/contentSecurityPolicy";
import { playRedirect } from "@/lib/playRoute";
import { settingsRedirect } from "@/lib/settingsCategory";
import { BACKEND_URL } from "@/lib/backend";

/** A backend that does not answer soon fails closed, as one that is down does. */
const ACCESS_CHECK_TIMEOUT_MS = 5000;

export async function proxy(request: NextRequest) {
  if (needsAccessCheck(request.nextUrl.pathname)) {
    try {
      const headers = new Headers({ cookie: request.headers.get("cookie") ?? "" });
      const ip = request.headers.get("x-eidolon-client-ip");
      if (ip) headers.set("x-eidolon-client-ip", ip);
      const checked = await fetch(`${BACKEND_URL}/api/access/status`, {
        headers, cache: "no-store", signal: AbortSignal.timeout(ACCESS_CHECK_TIMEOUT_MS),
      });
      if (!checked.ok) throw new Error("Access check failed");
      const state = await checked.json();
      if (!state.passed) {
        const target = new URL("/access", request.url);
        target.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search);
        const response = NextResponse.redirect(target);
        for (const cookie of checked.headers.getSetCookie()) response.headers.append("set-cookie", cookie);
        response.headers.set("Cache-Control", "no-store");
        response.headers.set("Content-Security-Policy", contentSecurityPolicy(process.env.EIDOLON_STAND_ASSETS_URL));
        return response;
      }
    } catch {
      return new NextResponse("暂时无法验证网站访问权限，请稍后重试", { status: 503, headers: { "Cache-Control": "no-store" } });
    }
  }
  const address = request.nextUrl.pathname + request.nextUrl.search;
  const to = settingsRedirect(address) ?? playRedirect(address);
  const response = to ? NextResponse.redirect(new URL(to, request.url)) : NextResponse.next();
  response.headers.set(
    "Content-Security-Policy",
    contentSecurityPolicy(process.env.EIDOLON_STAND_ASSETS_URL),
  );
  return response;
}

export const config = {
  // Not the API or Next's own files; what is served from public/ gets it too, harmlessly.
  matcher: ["/((?!api/|_next/).*)"],
};
