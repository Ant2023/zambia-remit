import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type MobileContainerProps = HTMLAttributes<HTMLDivElement> & {
  framed?: boolean;
};

export function MobileContainer({
  className,
  framed = false,
  ...props
}: MobileContainerProps) {
  return (
    <div className={cn("mbp-app-surface", framed && "py-0 sm:py-8")}>
      <div
        className={cn(
          "mbp-mobile-container",
          framed && "sm:min-h-[780px] sm:rounded-[2rem] sm:border sm:border-mbongo-line sm:shadow-mbongo-card",
          className,
        )}
        {...props}
      />
    </div>
  );
}

export const AppScreen = MobileContainer;
