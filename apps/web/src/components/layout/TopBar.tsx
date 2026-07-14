"use client";
import { Bell, ChevronDown, LogOut, Plus } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { notificationsApi } from "@/lib/api";

export function TopBar() {
  const { user, currentOrgId, currentOrg, logout, setCurrentOrg } = useAuthStore();
  const router = useRouter();
  const [unreadCount, setUnreadCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!user || !currentOrgId) return;

    // Fetch unread count
    notificationsApi
      .list(currentOrgId, { unread_only: true, limit: 1 })
      .then((r) => {
        // API returns array; length is used just as indicator here
      })
      .catch(() => {});

    // WebSocket for real-time notifications
    const ws = new WebSocket(
      `${process.env.NEXT_PUBLIC_API_URL?.replace("http", "ws")}/api/v1/notifications/ws/${user.id}`
    );
    ws.onmessage = () => setUnreadCount((c) => c + 1);
    wsRef.current = ws;
    return () => ws.close();
  }, [user, currentOrgId]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      {/* Org switcher */}
      <div className="flex items-center gap-2">
        {user?.organizations && user.organizations.length > 1 && (
          <select
            value={currentOrgId ?? ""}
            onChange={(e) => setCurrentOrg(e.target.value)}
            className="text-sm font-medium text-gray-700 border border-gray-200 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {user.organizations.map((org) => (
              <option key={org.organization_id} value={org.organization_id}>
                {org.organization_name}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* New Job quick action */}
        <button
          onClick={() => router.push("/dashboard/jobs/new")}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Job
        </button>

        {/* Notifications bell */}
        <button
          className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          onClick={() => router.push("/dashboard/notifications")}
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>

        {/* User menu */}
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          title="Sign out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
