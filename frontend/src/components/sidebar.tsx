"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, LayoutDashboard, Users, FileStack, FileText, Shield, LogOut, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { api, UserResponse } from "@/lib/api";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Patients", href: "/patients", icon: Users },
  { name: "Cases", href: "/cases", icon: FileStack },
  { name: "Reports", href: "/reports", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    setMounted(true);
    // Fetch current user or get role from token payload
    const token = localStorage.getItem("token");
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setUser({
          id: payload.sub,
          email: payload.email || "User",
          role: payload.role,
          is_active: true,
          created_at: "",
        });
      } catch (e) {
        console.error("Invalid token");
      }
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("token");
    router.push("/login");
  };

  const isAdmin = user?.role === "admin";

  return (
    <div className="flex h-full w-56 shrink-0 flex-col border-r border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
      <div className="flex h-14 shrink-0 items-center border-b border-slate-200 px-5 dark:border-slate-800">
        <Activity className="mr-2 h-5 w-5 text-teal-700 dark:text-teal-400" />
        <span className="text-base font-semibold tracking-tight text-slate-950 dark:text-white">MediScanX</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-5">
        {navigation.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                isActive
                  ? "bg-teal-50 text-teal-800 font-medium dark:bg-teal-950/40 dark:text-teal-300"
                  : "hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-900 dark:hover:text-white",
                "group flex items-center rounded-md px-3 py-2.5 text-sm transition-colors"
              )}
            >
              <item.icon
                className={cn(
                  isActive ? "text-teal-700 dark:text-teal-300" : "text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200",
                  "mr-3 h-5 w-5 flex-shrink-0 transition-colors"
                )}
                aria-hidden="true"
              />
              {item.name}
            </Link>
          );
        })}

        {isAdmin && (
          <Link
            href="/admin"
            className={cn(
              pathname.startsWith("/admin")
                ? "bg-teal-50 text-teal-800 font-medium dark:bg-teal-950/40 dark:text-teal-300"
                : "hover:bg-slate-100 hover:text-slate-950 dark:hover:bg-slate-900 dark:hover:text-white",
              "group flex items-center rounded-md px-3 py-2.5 text-sm transition-colors"
            )}
          >
            <Shield
              className={cn(
                pathname.startsWith("/admin") ? "text-teal-700 dark:text-teal-300" : "text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200",
                "mr-3 h-5 w-5 flex-shrink-0 transition-colors"
              )}
              aria-hidden="true"
            />
            Admin / Audit
          </Link>
        )}
      </nav>

      <div className="space-y-4 border-t border-slate-200 p-4 dark:border-slate-800">
        {mounted && (
          <div className="flex items-center justify-between px-2">
            <span className="text-xs font-medium text-slate-500">Theme</span>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-900 dark:hover:text-white"
              title="Toggle theme"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        )}
        
        <div className="flex items-center justify-between px-2">
          <div className="flex flex-col overflow-hidden">
            <span className="truncate text-sm font-medium text-slate-900 dark:text-white">{user?.role === 'admin' ? 'Administrator' : 'User'}</span>
            <span className="text-xs text-slate-500 truncate">{user?.id ? user.id.slice(0, 8) : ''}</span>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/30 dark:hover:text-red-300"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
