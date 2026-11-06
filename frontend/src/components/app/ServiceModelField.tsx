"use client";

import { useState } from "react";

import type { ModelLister } from "@/components/app/LLMProviderPicker";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxSelectTrigger,
} from "@/components/ui/combobox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";

const t = copy.llmPicker;

/** 中转把所有模型列在一起，生图的排在前面，一眼能看到。 */
export function imageModelsFirst(models: string[]): string[] {
  const forImages = (model: string) => /image|dall-?e|diffusion|flux/i.test(model);
  return [...models.filter(forImages), ...models.filter((m) => !forImages(m))];
}

/**
 * 生图服务的模型名：可以手填，也可以向服务问这把 key 能用哪些（`lister`，地址或 key 改了要重新问），
 * 从问到的里面选。没填好地址时 `lister` 是 null，按钮不能点。
 */
export function ServiceModelField({
  id,
  label,
  value,
  onChange,
  lister,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  lister: ModelLister | null;
  error: string | null;
}) {
  const [asking, setAsking] = useState<string | null>(null);
  const [listed, setListed] = useState<{ key: string; models: string[] } | null>(null);
  const [failed, setFailed] = useState<{ key: string; message: string } | null>(null);
  const models = lister && listed?.key === lister.key ? listed.models : null;
  const failure = lister && failed?.key === lister.key ? failed.message : null;
  const busy = !!lister && asking === lister.key;

  async function ask() {
    if (!lister) return;
    const { key } = lister;
    setAsking(key);
    setFailed(null);
    try {
      setListed({ key, models: imageModelsFirst(await lister.ask()) });
    } catch (e) {
      setFailed({ key, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setAsking((now) => (now === key ? null : now));
    }
  }

  return (
    <Field data-invalid={error ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="flex gap-2">
        <Input
          id={id}
          className="min-w-0 flex-1"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error ? true : undefined}
          autoComplete="off"
        />
        <Button type="button" variant="outline" disabled={!lister || busy} focusableWhenDisabled onClick={ask}>
          {busy && <Spinner data-icon="inline-start" />}
          {busy ? t.fetching : t.fetch}
        </Button>
      </div>
      {models && models.length > 0 && (
        <Combobox
          items={models}
          value={models.includes(value) ? value : null}
          onValueChange={(picked) => picked && onChange(picked)}
        >
          <ComboboxSelectTrigger aria-label={t.model} className="w-full" placeholder={t.modelPlaceholder} />
          <ComboboxContent>
            <ComboboxInput showTrigger={false} placeholder={t.modelSearch} />
            <ComboboxEmpty>{t.noModel}</ComboboxEmpty>
            <ComboboxList>
              {(model: string) => (
                <ComboboxItem key={model} value={model}>
                  <span className="truncate">{model}</span>
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      )}
      <div aria-live="polite">
        {failure ? (
          <FieldError>{failure}</FieldError>
        ) : (
          <FieldDescription>{models ? t.fetched(models.length) : lister ? t.imageModelHint : t.fetchNeedsKey}</FieldDescription>
        )}
      </div>
      {error && <FieldError>{error}</FieldError>}
    </Field>
  );
}
