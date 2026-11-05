"use client";

import { useSyncExternalStore } from "react";
import { emptyQueueSnapshot, queueSnapshot, subscribeQueue, type QueueKind } from "@/lib/serviceQueue";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const LABELS: Record<QueueKind, string> = { turn: "文字回复", call: "语音通话", bar: "酒吧回复", read_aloud: "朗读" };

export function ServiceQueueNotice() {
  const waiting = useSyncExternalStore(subscribeQueue, queueSnapshot, emptyQueueSnapshot);
  if (!waiting.length) return null;
  return (
    <aside aria-label="服务排队" className="fixed inset-x-4 bottom-6 z-100 mx-auto flex max-w-sm flex-col gap-2">
      {waiting.map((item) => (
        <Card key={item.id}>
          <CardContent className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1" role="status" aria-live="polite">
              <p className="text-sm font-medium">{LABELS[item.kind]}正在排队</p>
              <p className="text-xs text-muted-foreground">{item.position === null ? "正在获取排队位置…" : `当前第 ${item.position} 位`}</p>
              <p className="text-xs text-muted-foreground">管理员及六小时内使用较少的用户优先</p>
            </div>
            <Button variant="outline" size="sm" onClick={item.cancel}>取消排队</Button>
          </CardContent>
        </Card>
      ))}
    </aside>
  );
}
