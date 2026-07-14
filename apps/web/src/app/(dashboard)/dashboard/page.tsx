"use client";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, Users, Calendar, TrendingUp } from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { jobsApi, applicationsApi, interviewsApi } from "@/lib/api";

export default function DashboardPage() {
  const { currentOrgId } = useAuthStore();

  const { data: jobs } = useQuery({
    queryKey: ["jobs", currentOrgId],
    queryFn: () => jobsApi.list(currentOrgId!).then((r) => r.data),
    enabled: !!currentOrgId,
  });

  const { data: applications } = useQuery({
    queryKey: ["applications", currentOrgId],
    queryFn: () => applicationsApi.list(currentOrgId!).then((r) => r.data),
    enabled: !!currentOrgId,
  });

  const { data: interviews } = useQuery({
    queryKey: ["interviews", currentOrgId],
    queryFn: () => interviewsApi.list(currentOrgId!).then((r) => r.data),
    enabled: !!currentOrgId,
  });

  const publishedJobs = jobs?.filter((j: { status: string }) => j.status === "published").length ?? 0;
  const activeApplications = applications?.filter((a: { status: string }) => a.status === "active").length ?? 0;
  const upcomingInterviews = interviews?.filter(
    (i: { status: string }) => i.status === "scheduled" || i.status === "confirmed"
  ).length ?? 0;

  const stats = [
    { label: "Active Jobs", value: publishedJobs, icon: Briefcase, color: "bg-indigo-500" },
    { label: "Applications", value: activeApplications, icon: Users, color: "bg-violet-500" },
    { label: "Upcoming Interviews", value: upcomingInterviews, icon: Calendar, color: "bg-amber-500" },
    { label: "Hired This Month", value: 0, icon: TrendingUp, color: "bg-emerald-500" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
        <p className="text-gray-500 text-sm mt-1">Welcome back — here's what's happening.</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">{stat.label}</p>
              <div className={`w-9 h-9 ${stat.color} rounded-lg flex items-center justify-center`}>
                <stat.icon className="w-4 h-4 text-white" />
              </div>
            </div>
            <p className="text-3xl font-bold text-gray-900 mt-3">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Recent applications */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Recent Applications</h2>
        </div>
        <div className="divide-y divide-gray-50">
          {applications?.slice(0, 5).map((app: {
            id: string;
            candidate: { full_name: string; email: string };
            job: { title: string };
            current_stage: { name: string; color: string } | null;
            ai_score: number | null;
            applied_at: string;
          }) => (
            <div key={app.id} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center">
                  <span className="text-sm font-semibold text-indigo-700">
                    {app.candidate.full_name[0]}
                  </span>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-900">{app.candidate.full_name}</p>
                  <p className="text-xs text-gray-500">{app.job.title}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {app.current_stage && (
                  <span
                    className="text-xs font-medium px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: `${app.current_stage.color}20`, color: app.current_stage.color }}
                  >
                    {app.current_stage.name}
                  </span>
                )}
                {app.ai_score !== null && (
                  <span className="text-xs font-semibold text-gray-700 bg-gray-100 px-2 py-0.5 rounded-full">
                    AI {app.ai_score}%
                  </span>
                )}
              </div>
            </div>
          ))}
          {!applications?.length && (
            <div className="px-6 py-10 text-center text-gray-400 text-sm">No applications yet</div>
          )}
        </div>
      </div>

      {/* Upcoming interviews */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Upcoming Interviews</h2>
        </div>
        <div className="divide-y divide-gray-50">
          {interviews
            ?.filter((i: { status: string }) => ["scheduled", "confirmed"].includes(i.status))
            .slice(0, 5)
            .map((interview: {
              id: string;
              title: string;
              candidate: { full_name: string };
              scheduled_at: string;
              duration_minutes: number;
              status: string;
            }) => (
              <div key={interview.id} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
                <div>
                  <p className="text-sm font-medium text-gray-900">{interview.title}</p>
                  <p className="text-xs text-gray-500">{interview.candidate.full_name}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-700">
                    {new Date(interview.scheduled_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </p>
                  <p className="text-xs text-gray-400">{interview.duration_minutes} min</p>
                </div>
              </div>
            ))}
          {!upcomingInterviews && (
            <div className="px-6 py-10 text-center text-gray-400 text-sm">No upcoming interviews</div>
          )}
        </div>
      </div>
    </div>
  );
}
