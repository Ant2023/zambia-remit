import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Card } from "./Card";

type FormSectionProps = HTMLAttributes<HTMLDivElement> & {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
};

export function FormSection({
  title,
  description,
  action,
  className,
  children,
  ...props
}: FormSectionProps) {
  return (
    <Card className={cn("space-y-5", className)} {...props}>
      <div className="flex flex-col gap-3 border-b border-mbongo-line pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h2 className="text-lg font-bold leading-tight text-mbongo-navy">{title}</h2>
          {description ? (
            <p className="text-sm leading-6 text-mbongo-muted">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className="grid gap-4">{children}</div>
    </Card>
  );
}
