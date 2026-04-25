import { cn } from "@/lib/cn";

type StatusTone = "success" | "warning" | "error" | "info";

const toneClasses: Record<StatusTone, string> = {
  success: "mbp-status-success",
  warning: "mbp-status-warning",
  error: "mbp-status-error",
  info: "mbp-status-info",
};

type StatusBadgeProps = {
  children: React.ReactNode;
  tone?: StatusTone;
  className?: string;
};

export function StatusBadge({
  children,
  tone = "info",
  className,
}: StatusBadgeProps) {
  return (
    <span className={cn("mbp-status-badge", toneClasses[tone], className)}>
      {children}
    </span>
  );
}
