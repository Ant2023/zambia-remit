import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type DashboardLayoutProps = {
  children: ReactNode;
  sidebar?: ReactNode;
  topBar?: ReactNode;
  className?: string;
};

export function DashboardLayout({
  children,
  sidebar,
  topBar,
  className,
}: DashboardLayoutProps) {
  return (
    <div className={cn("mbp-dashboard-layout", className)}>
      <div className="border-b border-mbongo-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center px-4 sm:px-6 lg:px-8">
          {topBar}
        </div>
      </div>
      <div className="mbp-dashboard-shell">
        {sidebar ? <aside className="mbp-dashboard-sidebar">{sidebar}</aside> : null}
        <main className={cn("mbp-dashboard-main", !sidebar && "lg:col-span-2")}>
          {children}
        </main>
      </div>
    </div>
  );
}
