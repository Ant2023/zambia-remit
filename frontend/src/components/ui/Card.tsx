import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  padded?: boolean;
};

export function Card({ className, padded = true, ...props }: CardProps) {
  return (
    <div
      className={cn(padded ? "mbp-card-padded" : "mbp-card", className)}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  title,
  description,
  action,
}: {
  className?: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div className="space-y-1">
        <h2 className="text-lg font-bold leading-tight text-mbongo-navy">{title}</h2>
        {description ? (
          <p className="text-sm leading-6 text-mbongo-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
