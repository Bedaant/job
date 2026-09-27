"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EXTENSION_POLL_MS, extensionStatusView } from "@/lib/extension";
import { cn } from "@/lib/utils";

/** Live "is the extension connected?" line. Polls only while the tab is visible
 *  (react-query skips interval refetches in background tabs by default). */
export function ExtensionStatus({ className }: { className?: string }) {
  const query = useQuery({
    queryKey: ["extension-status"],
    queryFn: api.getExtensionStatus,
    refetchInterval: EXTENSION_POLL_MS,
    retry: false,
  });
  const view = extensionStatusView(query.data, query.isError);

  return (
    <p role="status" aria-live="polite" className={cn("flex items-center gap-2 text-sm", className)}>
      <span
        aria-hidden="true"
        className={cn("h-2 w-2 shrink-0 rounded-full", view.connected ? "bg-primary" : "bg-muted-foreground/50")}
      />
      <span className={view.connected ? "font-medium" : "text-muted-foreground"}>{view.text}</span>
    </p>
  );
}
