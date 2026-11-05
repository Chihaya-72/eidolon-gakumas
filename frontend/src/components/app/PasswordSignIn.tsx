"use client";

import { FormEvent, useId, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { copy } from "@/i18n";
import { passwordLogin, passwordRegister } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.login;

/**
 * 用名称和密码登录或注册（`EIDOLON_PASSWORD_LOGIN=1`）。名称的规矩在后端（`passwords`），这里只把它说出来；
 * 两次密码是否一致只有这里查：密码目前找不回，打错了就进不来。
 */
export function PasswordSignIn({ invite }: { invite?: string | null }) {
  const id = useId();
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (registering && password !== again) {
      setFailure({ message: t.passwordsDiffer, signedOut: false });
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      if (registering) await passwordRegister(username, password, invite);
      else await passwordLogin(username, password);
      window.location.assign("/conversations");
    } catch (e) {
      // 这里本来就是登录的地方，不再给「去登录」的链接。
      setFailure({ ...toFailure(e), signedOut: false });
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field>
        <FieldLabel htmlFor={`${id}-name`}>{t.username}</FieldLabel>
        <Input
          id={`${id}-name`}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
        />
        {registering && <FieldDescription>{t.usernameRule}</FieldDescription>}
      </Field>
      <Field>
        <FieldLabel htmlFor={`${id}-password`}>{t.password}</FieldLabel>
        <Input
          id={`${id}-password`}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={registering ? "new-password" : "current-password"}
          required
        />
        {registering && <FieldDescription>{t.passwordRule}</FieldDescription>}
      </Field>
      {registering && (
        <Field>
          <FieldLabel htmlFor={`${id}-again`}>{t.passwordAgain}</FieldLabel>
          <Input
            id={`${id}-again`}
            type="password"
            value={again}
            onChange={(e) => setAgain(e.target.value)}
            autoComplete="new-password"
            required
          />
        </Field>
      )}
      {failure && <FailureNotice failure={failure} />}
      <Button type="submit" size="lg" className="w-full" disabled={busy}>
        {busy ? t.guestBusy : registering ? t.registerSubmit : t.passwordSubmit}
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="w-full"
        disabled={busy}
        onClick={() => {
          setRegistering(!registering);
          setFailure(null);
        }}
      >
        {registering ? t.toSignIn : t.toRegister}
      </Button>
    </form>
  );
}
