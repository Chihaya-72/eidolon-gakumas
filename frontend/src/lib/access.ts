/** Only local paths may be used after the password form, including invitation queries. */
export function accessReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\x00-\x20\x7f]/.test(value)) return "/";
  return value.split("?")[0] === "/access" ? "/" : value;
}

export type AccessState = { enabled: boolean; passed: boolean; banned: boolean; remaining?: number; detail?: string };
export type AccessSettings = { enabled: boolean; password_set: boolean };
export type AccessBan = { id: string; browser: string; ip: string; banned_at: string };
