"use client";

import { useEffect, useState, type FormEvent } from "react";
import { accessReturnTo, type AccessState } from "@/lib/access";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";

export function AccessEntry() {
  const [state, setState] = useState<AccessState | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function enter() {
    window.location.replace(accessReturnTo(new URLSearchParams(window.location.search).get("returnTo")));
  }

  useEffect(() => {
    let active = true;
    fetch("/api/access/status", { cache: "no-store" }).then(async (response) => {
      if (!response.ok) throw new Error("暂时无法验证访问权限，请稍后重试");
      const value: AccessState = await response.json();
      if (!active) return;
      setState(value);
      if (value.passed) enter();
    }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || state?.banned) return;
    setBusy(true);
    setError("");
    try {
      // Password entry is separate from account login; a wrong password must not redirect to login.
      const response = await fetch("/api/access/verify", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const value: AccessState = await response.json();
      setState(value);
      setPassword("");
      if (value.passed) enter();
      else setError(value.detail ?? "暂时无法验证，请稍后重试");
    } catch {
      setError("暂时无法连接服务器，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle><h1>网站访问密码</h1></CardTitle>
          <CardDescription>输入管理员提供的访问密码后继续。</CardDescription>
        </CardHeader>
        <CardContent>
          {state?.banned ? (
            <p role="alert" className="text-sm">此浏览器或 IP 已被封禁，请联系管理员解除。</p>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-4">
              <Field>
                <FieldLabel htmlFor="access-password">访问密码</FieldLabel>
                <Input id="access-password" type="password" autoComplete="current-password" maxLength={128}
                  value={password} onChange={(event) => setPassword(event.target.value)} required disabled={busy || !state} />
              </Field>
              <p className="text-sm text-muted-foreground">连续三次输入失败将封禁此浏览器和 IP。</p>
              {typeof state?.remaining === "number" && <p className="text-sm" role="status">还可尝试 {state.remaining} 次</p>}
              {error && <p className="text-sm" role="alert">{error}</p>}
              {!state && !error && <p role="status" className="text-sm text-muted-foreground">正在检查访问权限…</p>}
              <Button type="submit" disabled={busy || !state || !password}>{busy ? "正在验证…" : "进入网站"}</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
