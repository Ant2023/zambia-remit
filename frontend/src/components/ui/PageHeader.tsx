import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type PageHeaderProps = {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
};

export function PageHeader({
  title,
  eyebrow,
  description,
  action,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="max-w-3xl space-y-2">
        {eyebrow ? <p className="mbp-page-kicker">{eyebrow}</p> : null}
        <h1 className="mbp-page-title">{title}</h1>
        {description ? (
          <p className="text-base leading-7 text-mbongo-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="w-full sm:w-auto">{action}</div> : null}
    </header>
  );
}
