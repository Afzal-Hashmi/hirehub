"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { superAdminApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Building2, Users, ToggleLeft, ToggleRight } from "lucide-react";

const FLAG_LABELS: Record<string, string> = {
  ai_resume_scoring: "AI Resume Scoring",
  ai_question_gen: "AI Question Generation",
  ai_fit_analysis: "AI Fit Analysis",
  ai_email_drafting: "AI Email Drafting",
  google_calendar_sync: "Google Calendar Sync",
  slack_notifications: "Slack Notifications",
  sms_notifications: "SMS Notifications",
  whatsapp_notifications: "WhatsApp Notifications",
  candidate_self_booking: "Candidate Self-Booking",
  public_job_board: "Public Job Board",
  analytics_dashboard: "Analytics Dashboard",
  bulk_import: "Bulk Import",
  offer_letter_gen: "Offer Letter Generation",
  video_interviews: "Video Interviews",
  custom_pipeline_stages: "Custom Pipeline Stages",
};

export default function SuperAdminPage() {
  const { isSuperAdmin } = useAuthStore();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [selectedOrg, setSelectedOrg] = useState<string | null>(null);

  if (!isSuperAdmin) {
    router.replace("/dashboard");
    return null;
  }

  const { data: stats } = useQuery({
    queryKey: ["superadmin-stats"],
    queryFn: () => superAdminApi.getStats().then((r) => r.data),
  });

  const { data: orgs } = useQuery({
    queryKey: ["superadmin-orgs"],
    queryFn: () => superAdminApi.listOrgs().then((r) => r.data),
  });

  const { data: orgDetail } = useQuery({
    queryKey: ["superadmin-org", selectedOrg],
    queryFn: () => superAdminApi.getOrg(selectedOrg!).then((r) => r.data),
    enabled: !!selectedOrg,
  });

  const updateFlagMutation = useMutation({
    mutationFn: ({ orgId, flag, value }: { orgId: string; flag: string; value: boolean }) =>
      superAdminApi.updateFeatureFlags(orgId, { [flag]: value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["superadmin-org", selectedOrg] });
      queryClient.invalidateQueries({ queryKey: ["superadmin-orgs"] });
      toast.success("Feature flag updated");
    },
  });

  const updateSeatsMutation = useMutation({
    mutationFn: ({ orgId, seats }: { orgId: string; seats: number }) =>
      superAdminApi.updateSeats(orgId, seats),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["superadmin-org", selectedOrg] });
      toast.success("Seat limit updated");
    },
  });

  const toggleOrgMutation = useMutation({
    mutationFn: ({ orgId, active }: { orgId: string; active: boolean }) =>
      superAdminApi.updateOrgStatus(orgId, active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["superadmin-orgs"] });
      toast.success("Organization status updated");
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Super Admin</h1>
        <p className="text-sm text-gray-500 mt-1">Platform-wide management</p>
      </div>

      {/* Platform stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Organizations", value: stats.organizations, icon: Building2 },
            { label: "Users", value: stats.users, icon: Users },
            { label: "Jobs", value: stats.jobs, icon: Building2 },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-sm text-gray-500">{s.label}</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-6">
        {/* Org list */}
        <div className="w-80 bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 font-semibold text-sm text-gray-700">
            Organizations
          </div>
          <div className="divide-y divide-gray-50 max-h-[60vh] overflow-y-auto">
            {orgs?.items?.map((org: {
              id: string;
              name: string;
              slug: string;
              is_active: boolean;
              member_count: number;
              max_seats: number;
            }) => (
              <button
                key={org.id}
                onClick={() => setSelectedOrg(org.id)}
                className={`w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors ${
                  selectedOrg === org.id ? "bg-indigo-50" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{org.name}</p>
                    <p className="text-xs text-gray-400">{org.slug}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{org.member_count}/{org.max_seats + 1}</span>
                    <div
                      className={`w-2 h-2 rounded-full ${org.is_active ? "bg-emerald-500" : "bg-red-400"}`}
                    />
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Org detail + feature flags */}
        {orgDetail && (
          <div className="flex-1 bg-white rounded-xl border border-gray-200">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <div>
                <h2 className="font-semibold text-gray-900">{orgDetail.name}</h2>
                <p className="text-xs text-gray-400">{orgDetail.slug}</p>
              </div>
              <div className="flex items-center gap-3">
                {/* Seat limit editor */}
                <div className="flex items-center gap-2">
                  <label className="text-xs text-gray-500">Max seats</label>
                  <input
                    type="number"
                    defaultValue={orgDetail.max_seats}
                    min={1}
                    className="w-16 text-sm border border-gray-200 rounded px-2 py-1 text-center"
                    onBlur={(e) =>
                      updateSeatsMutation.mutate({
                        orgId: orgDetail.id,
                        seats: parseInt(e.target.value),
                      })
                    }
                  />
                </div>
                {/* Activate/deactivate */}
                <button
                  onClick={() =>
                    toggleOrgMutation.mutate({ orgId: orgDetail.id, active: !orgDetail.is_active })
                  }
                  className={`text-xs font-medium px-3 py-1.5 rounded-lg ${
                    orgDetail.is_active
                      ? "bg-red-50 text-red-600 hover:bg-red-100"
                      : "bg-emerald-50 text-emerald-600 hover:bg-emerald-100"
                  }`}
                >
                  {orgDetail.is_active ? "Deactivate" : "Activate"}
                </button>
              </div>
            </div>

            <div className="px-6 py-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Feature Flags</h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(orgDetail.feature_flags ?? {}).map(([flag, enabled]) => (
                  <div
                    key={flag}
                    className="flex items-center justify-between p-3 rounded-lg border border-gray-100 hover:bg-gray-50"
                  >
                    <span className="text-sm text-gray-700">{FLAG_LABELS[flag] ?? flag}</span>
                    <button
                      onClick={() =>
                        updateFlagMutation.mutate({
                          orgId: orgDetail.id,
                          flag,
                          value: !enabled,
                        })
                      }
                      className={`shrink-0 ${enabled ? "text-indigo-600" : "text-gray-300"}`}
                    >
                      {enabled ? (
                        <ToggleRight className="w-6 h-6" />
                      ) : (
                        <ToggleLeft className="w-6 h-6" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {!selectedOrg && (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm bg-white rounded-xl border border-gray-200">
            Select an organization to manage
          </div>
        )}
      </div>
    </div>
  );
}
