import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/i18n";
import type { SignInOptions } from "@/lib/api";
import { REPOSITORY_URL } from "@/lib/repository";
import { PROVIDER_LABELS } from "@/lib/signIn";

import { IDOL_COLORS, inkOn, shade, type WelcomeIdol } from "./welcome/idols";
import { Welcome } from "./welcome/Welcome";

const t = copy.landing;

/** 透明底的《学园偶像大师》标志（白底已扣掉），第二页天空里的那一个和入口页的小标志。 */
const LOGO = "/landing/welcome/gakumas-logo.webp";

/**
 * 落地页（ADR-0016）：`/` 和 `/about` 共用，现在是欢迎页（welcome/Welcome.tsx）的五页。文案、颜色和入口按钮的
 * 类名都在服务端算好，传给客户端组件的只有字符串和数：文案目录和 cn 不进落地页的包。
 */
export function Landing({ isSignedIn, signInOptions }: { isSignedIn: boolean; signInOptions: SignInOptions | null }) {
  const w = t.welcome;
  const idols: WelcomeIdol[] = IDOL_COLORS.map(({ id, color }) => {
    const words = w.idols[id];
    return {
      id,
      color,
      ink: inkOn(color),
      deep: shade(color, 0.35),
      ja: words.ja,
      short: words.short,
      call: words.call,
      exam: words.exam,
      chatter: [...words.chatter],
    };
  });
  return (
    <Welcome
      appName={w.intro.title}
      description={copy.app.description}
      disclaimer={t.disclaimer}
      copy={{
        intro: { ...w.intro, features: [...w.intro.features] },
        stage: { ...w.stage, producer: [...w.stage.producer], ruleTop: [...w.stage.ruleTop], ruleBottom: [...w.stage.ruleBottom] },
        call: w.call,
        memory: w.memory,
        entry: w.entry,
      }}
      idols={idols}
      isSignedIn={isSignedIn}
      entryLabel={isSignedIn ? t.continue : t.signIn}
      entryClassName={{
        header: buttonVariants({ variant: "outline" }),
        large: buttonVariants({ size: "lg" }),
        repo: buttonVariants({ variant: "ghost" }),
      }}
      repository={{ url: REPOSITORY_URL, label: copy.app.repositoryLabel }}
      notices={honestyLines(signInOptions)}
      legal={{ disclaimer: copy.legal.disclaimer, privacy: copy.legal.privacy, terms: copy.legal.terms }}
      logoSrc={LOGO}
    />
  );
}

/**
 * 使用须知的几句话；登录方式从后端的登录选项读出来，一种都没有时说暂时不能登录。和登录组件（SignInChoices）
 * 说法一致：开着开发登录时不说不能登录；取不到登录选项时不提。
 */
function honestyLines(options: SignInOptions | null): string[] {
  const lines = [t.act6.unofficial, t.act6.limits, t.act6.ownKey, t.act6.memories, t.act6.affinity];
  if (!options || (options.providers.length === 0 && options.dev_login)) return lines;
  const providers = options.providers.map((p) => PROVIDER_LABELS[p]);
  return [...lines, providers.length > 0 ? t.act6.signIn(providers.join(` ${t.act6.or} `)) : t.act6.noSignIn];
}
