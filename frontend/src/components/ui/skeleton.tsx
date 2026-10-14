import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Placeholder de carregamento (pulse) no tom muted. */
export function Skeleton({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}
