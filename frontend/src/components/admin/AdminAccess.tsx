"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, json } from "@/lib/api";
import type { AccessBan, AccessSettings } from "@/lib/access";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** The password is write-only; a blank field preserves the existing password. */
export function AdminAccess() {
  const [settings, setSettings] = useState<AccessSettings | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [password, setPassword] = useState("");
  const [bans, setBans] = useState<AccessBan[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      api("/api/admin/access").then(json<AccessSettings>),
      api("/api/admin/access/bans").then(json<AccessBan[]>),
    ]).then(([value, blocked]) => {
      if (!active) return;
      setSettings(value); setEnabled(value.enabled); setBans(blocked);
    }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(""); setSaved(false);
    try {
      const value = await json<AccessSettings>(await api("/api/admin/access", {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ enabled, ...(password ? { password } : {}) }),
      }));
      setSettings(value); setEnabled(value.enabled); setPassword(""); setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  async function unban(id: string) {
    setBusy(true); setError("");
    try {
      const response = await api(`/api/admin/access/bans/${id}`, { method: "DELETE" });
      if (!response.ok) await json(response);
      setBans(await json<AccessBan[]>(await api("/api/admin/access/bans")));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <>
      {error && <p role="alert" className="text-sm">{error}</p>}
      <Card>
        <CardHeader>
          <CardTitle><h2>密码访问</h2></CardTitle>
          <CardDescription>开启后，访客和已登录用户都需要先输入访问密码。三次失败将封禁浏览器和 IP，共用 IP 的其他访客也会受到影响。</CardDescription>
        </CardHeader>
        <CardContent>
          {!settings ? <p role="status" className="text-sm text-muted-foreground">正在读取…</p> : (
            <form onSubmit={save} className="flex flex-col gap-4">
              <Field orientation="horizontal">
                <FieldLabel htmlFor="access-enabled">开启密码访问</FieldLabel>
                <Switch id="access-enabled" checked={enabled} onCheckedChange={(value) => { setEnabled(value); setSaved(false); }} disabled={busy} />
              </Field>
              <Field>
                <FieldLabel htmlFor="site-password">{settings.password_set ? "修改访问密码" : "设置访问密码"}</FieldLabel>
                <Input id="site-password" type="password" autoComplete="new-password" minLength={8} maxLength={128}
                  required={enabled && !settings.password_set} value={password}
                  onChange={(event) => { setPassword(event.target.value); setSaved(false); }} disabled={busy} />
                <p className="text-sm text-muted-foreground">8 至 128 个字符。{settings.password_set ? "留空保留现有密码。" : ""}修改后其他浏览器需重新验证，通行有效期为 30 天。</p>
              </Field>
              <div className="flex items-center gap-3">
                <Button type="submit" disabled={busy}>{busy ? "正在保存…" : "保存"}</Button>
                {saved && <p role="status" className="text-sm text-muted-foreground">已保存</p>}
              </div>
            </form>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle><h2>访问黑名单</h2></CardTitle>
          <CardDescription>解除一条封禁会同时解除对应浏览器及 IP 的封禁并清零失败次数。下方显示匿名标识。</CardDescription>
        </CardHeader>
        <CardContent>
          {bans.length === 0 ? <p className="text-sm text-muted-foreground">暂无访问封禁</p> : (
            <Table>
              <TableHeader><TableRow><TableHead>浏览器</TableHead><TableHead>IP 标识</TableHead><TableHead>封禁时间</TableHead><TableHead>操作</TableHead></TableRow></TableHeader>
              <TableBody>{bans.map((ban) => (
                <TableRow key={ban.id}>
                  <TableCell>{ban.browser}</TableCell><TableCell>{ban.ip}</TableCell>
                  <TableCell>{new Date(ban.banned_at).toLocaleString("zh-CN")}</TableCell>
                  <TableCell><Button variant="outline" size="sm" disabled={busy} onClick={() => void unban(ban.id)}>解除封禁</Button></TableCell>
                </TableRow>
              ))}</TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle><h2>服务排队</h2></CardTitle>
          <CardDescription>使用本站主要 API 的操作共用一个队列。管理员优先，其余按最近六小时使用次数由少到多排序，同次数先到先服务；正在进行的操作不会被打断。主要 API 全部自带时免排队。</CardDescription>
        </CardHeader>
      </Card>
    </>
  );
}
