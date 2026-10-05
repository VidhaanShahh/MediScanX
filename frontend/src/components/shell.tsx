"use client";

import { ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { usePathname } from "next/navigation";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login" || pathname === "/register") {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#f6f8f9] dark:bg-slate-950">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 shrink-0 border-b border-slate-200 bg-white/90 px-6 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90 md:px-8">
          <div className="flex-1">
            <p className="text-xs font-medium tracking-wide text-slate-500">MediScanX <span className="mx-1 text-slate-300">/</span> Screening workspace</p>
          </div>
        </header>
        <main className="flex-1 overflow-auto px-5 py-7 md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
