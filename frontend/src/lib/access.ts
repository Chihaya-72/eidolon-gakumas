/** Only local paths may be used after the password form, including invitation queries. */
export function accessReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\x00-\x20\x7f]/.test(value)) return "/";
  return value.split("?")[0] === "/access" ? "/" : value;
}

const STATIC_FILE = /\.(?:avif|gif|ico|jpe?g|mp3|ogg|png|svg|wav|webp|woff2?)$/i;

/** Pictures, sounds and fonts hold nothing the gate protects, and one page asks for many of them;
 * pages still ask the backend, and every business API checks for itself. */
export function needsAccessCheck(pathname: string): boolean {
  return pathname !== "/access" && !STATIC_FILE.test(pathname);
}

export type AccessState = { enabled: boolean; passed: boolean; banned: boolean; remaining?: number; detail?: string };
export type AccessSettings = { enabled: boolean; password_set: boolean };
export type AccessBan = { id: string; browser: string; ip: string; banned_at: string };
