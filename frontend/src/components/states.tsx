import { AlertTriangle, DatabaseZap, Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { isSnapshotUnavailable } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Skeleton genérico para preencher um tile enquanto carrega. */
export function LoadingState({ className }: { className?: string }) {
  return (
    <div
      className={cn("flex h-full flex-col gap-3", className)}
      role="status"
      aria-label="Carregando"
    >
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-10 w-2/3" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

function StateShell({
  icon,
  title,
  children,
  tone = "muted",
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  tone?: "muted" | "destructive";
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-6 text-center">
      <div
        className={cn(
          "mb-1",
          tone === "destructive" ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {icon}
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {children && (
        <p className="max-w-xs text-xs text-muted-foreground">{children}</p>
      )}
    </div>
  );
}

/**
 * Traduz um erro em mensagem acionável. O 503 (snapshot indisponível) tem
 * copy própria porque é um estado operacional esperado, não um bug.
 */
export function ErrorState({ error }: { error: unknown }) {
  if (isSnapshotUnavailable(error)) {
    return (
      <StateShell
        icon={<DatabaseZap className="h-6 w-6" aria-hidden />}
        title="Snapshot indisponível"
      >
        Nenhum snapshot publicado ainda. Rode o pipeline no Dagster para
        materializar e publicar os dados Gold.
      </StateShell>
    );
  }
  const message =
    error instanceof Error ? error.message : "Erro inesperado ao carregar.";
  return (
    <StateShell
      icon={<AlertTriangle className="h-6 w-6" aria-hidden />}
      title="Não foi possível carregar"
      tone="destructive"
    >
      {message}
    </StateShell>
  );
}

/** Resposta chegou, mas sem linhas para exibir. */
export function EmptyState({
  title = "Sem dados",
  children,
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <StateShell
      icon={<Inbox className="h-6 w-6" aria-hidden />}
      title={title}
    >
      {children}
    </StateShell>
  );
}
