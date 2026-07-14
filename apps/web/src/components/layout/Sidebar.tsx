"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Briefcase,
  Users,
  Calendar,
  LayoutKanban,
  BarChart2,
  Settings,
  UserCog,
  Building2,
  Sparkles,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore, useFeatureFlagsStore } from "@/lib/store";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: BarChart2 },
  { href: "/dashboard/jobs", label: "Jobs", icon: Briefcase },
  { href: "/dashboard/candidates", label: "Candidates", icon: Users },
  { href: "/dashboard/pipeline", label: "Pipeline", icon: LayoutKanban },
  { href: "/dashboard/interviews", label: "Interviews", icon: Calendar },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart2, flag: "analytics_dashboard" },
  { href: "/dashboard/team", label: "Team", icon: UserCog },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

const superAdminItems = [
  { href: "/superadmin", label: "Organizations", icon: Building2 },
  { href: "/superadmin/users", label: "Users", icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, currentOrg, isSuperAdmin } = useAuthStore();
  const { hasFlag } = useFeatureFlagsStore();

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-gray-900 text-lg">HireHub</span>
        </div>
      </div>

      {/* Org badge */}
      {currentOrg && (
        <div className="px-4 py-3 border-b border-gray-100">
          <div className="flex items-center gap-2 px-2 py-1.5 bg-indigo-50 rounded-md">
            <Building2 className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
            <span className="text-xs font-medium text-indigo-700 truncate">{currentOrg.organization_name}</span>
          </div>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          if (item.flag && !hasFlag(item.flag)) return null;
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                active
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )}
            >
              <item.icon className="w-4 h-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}

        {isSuperAdmin && (
          <>
            <div className="pt-4 pb-2">
              <div className="flex items-center gap-1.5 px-3">
                <Shield className="w-3 h-3 text-rose-500" />
                <span className="text-xs font-semibold text-rose-500 uppercase tracking-wider">Super Admin</span>
              </div>
            </div>
            {superAdminItems.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    active ? "bg-rose-50 text-rose-700" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  )}
                >
                  <item.icon className="w-4 h-4 shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </>
        )}
      </nav>

      {/* User footer */}
      <div className="p-4 border-t border-gray-200">
        <div className="flex items-center gap-3">
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="" className="w-8 h-8 rounded-full" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
              <span className="text-xs font-semibold text-indigo-700">
                {user?.full_name?.[0]?.toUpperCase()}
              </span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name}</p>
            <p className="text-xs text-gray-500 truncate">{currentOrg?.role}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
