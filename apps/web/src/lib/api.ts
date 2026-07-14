import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function createApiClient(orgId?: string): AxiosInstance {
  const client = axios.create({
    baseURL: `${BASE_URL}/api/v1`,
    headers: {
      "Content-Type": "application/json",
      ...(orgId ? { "x-organization-id": orgId } : {}),
    },
  });

  client.interceptors.request.use((config) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("hirehub_access_token");
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  });

  client.interceptors.response.use(
    (res) => res,
    async (error) => {
      if (error.response?.status === 401 && typeof window !== "undefined") {
        const refreshToken = localStorage.getItem("hirehub_refresh_token");
        if (refreshToken) {
          try {
            const { data } = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
              refresh_token: refreshToken,
            });
            localStorage.setItem("hirehub_access_token", data.access_token);
            localStorage.setItem("hirehub_refresh_token", data.refresh_token);
            error.config.headers.Authorization = `Bearer ${data.access_token}`;
            return client.request(error.config);
          } catch {
            localStorage.clear();
            window.location.href = "/login";
          }
        }
      }
      return Promise.reject(error);
    }
  );

  return client;
}

export const api = createApiClient();

export function orgApi(orgId: string) {
  return createApiClient(orgId);
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  exchangeOAuth: (provider: string, accessToken: string) =>
    api.post("/auth/oauth/exchange", { provider, access_token: accessToken }),
  getMe: () => api.get("/auth/me"),
};

// ─── Organizations ────────────────────────────────────────────────────────────

export const orgsApi = {
  create: (data: { name: string; website?: string; industry?: string }) =>
    api.post("/organizations", data),
  get: (orgId: string) => orgApi(orgId).get(`/organizations/${orgId}`),
  update: (orgId: string, data: Record<string, unknown>) =>
    orgApi(orgId).patch(`/organizations/${orgId}`, data),
  listMembers: (orgId: string) => orgApi(orgId).get(`/organizations/${orgId}/members`),
  inviteMember: (orgId: string, email: string, role: string) =>
    orgApi(orgId).post(`/organizations/${orgId}/invite`, { email, role }),
  acceptInvite: (token: string) => api.post(`/organizations/invite/accept/${token}`),
  getFeatureFlags: (orgId: string) => orgApi(orgId).get(`/organizations/${orgId}/feature-flags`),
};

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export const jobsApi = {
  list: (orgId: string, params?: Record<string, unknown>) =>
    orgApi(orgId).get("/jobs", { params }),
  get: (orgId: string, jobId: string) => orgApi(orgId).get(`/jobs/${jobId}`),
  create: (orgId: string, data: Record<string, unknown>) => orgApi(orgId).post("/jobs", data),
  update: (orgId: string, jobId: string, data: Record<string, unknown>) =>
    orgApi(orgId).patch(`/jobs/${jobId}`, data),
  publish: (orgId: string, jobId: string) => orgApi(orgId).post(`/jobs/${jobId}/publish`),
  close: (orgId: string, jobId: string) => orgApi(orgId).post(`/jobs/${jobId}/close`),
  updateStages: (orgId: string, jobId: string, stages: unknown[]) =>
    orgApi(orgId).patch(`/jobs/${jobId}/stages`, { stages }),
};

// ─── Candidates ───────────────────────────────────────────────────────────────

export const candidatesApi = {
  list: (orgId: string, params?: Record<string, unknown>) =>
    orgApi(orgId).get("/candidates", { params }),
  get: (orgId: string, candidateId: string) => orgApi(orgId).get(`/candidates/${candidateId}`),
  create: (orgId: string, data: Record<string, unknown>) => orgApi(orgId).post("/candidates", data),
  uploadResume: (orgId: string, candidateId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return orgApi(orgId).post(`/candidates/${candidateId}/resume`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};

// ─── Applications ─────────────────────────────────────────────────────────────

export const applicationsApi = {
  list: (orgId: string, params?: Record<string, unknown>) =>
    orgApi(orgId).get("/applications", { params }),
  get: (orgId: string, appId: string) => orgApi(orgId).get(`/applications/${appId}`),
  moveStage: (orgId: string, appId: string, stageId: string) =>
    orgApi(orgId).patch(`/applications/${appId}/stage`, { stage_id: stageId }),
  reject: (orgId: string, appId: string, data: Record<string, unknown>) =>
    orgApi(orgId).post(`/applications/${appId}/reject`, data),
  addNote: (orgId: string, appId: string, note: string) =>
    orgApi(orgId).post(`/applications/${appId}/notes`, { note }),
  triggerAiScoring: (orgId: string, appId: string) =>
    orgApi(orgId).post(`/applications/${appId}/trigger-ai-scoring`),
};

// ─── Interviews ───────────────────────────────────────────────────────────────

export const interviewsApi = {
  list: (orgId: string, params?: Record<string, unknown>) =>
    orgApi(orgId).get("/interviews", { params }),
  get: (orgId: string, interviewId: string) => orgApi(orgId).get(`/interviews/${interviewId}`),
  schedule: (orgId: string, data: Record<string, unknown>) => orgApi(orgId).post("/interviews", data),
  sendSelfBooking: (orgId: string, data: Record<string, unknown>) =>
    orgApi(orgId).post("/interviews/self-booking/send", data),
  getSelfBooking: (token: string) => api.get(`/interviews/self-booking/${token}`),
  confirmSelfBooking: (token: string, data: Record<string, unknown>) =>
    api.post(`/interviews/self-booking/${token}/confirm`, data),
  submitFeedback: (orgId: string, interviewId: string, data: Record<string, unknown>) =>
    orgApi(orgId).post(`/interviews/${interviewId}/feedback`, data),
  generateQuestions: (orgId: string, interviewId: string) =>
    orgApi(orgId).post(`/interviews/${interviewId}/generate-questions`),
  cancel: (orgId: string, interviewId: string) =>
    orgApi(orgId).patch(`/interviews/${interviewId}/cancel`),
};

// ─── AI ───────────────────────────────────────────────────────────────────────

export const aiApi = {
  draftEmail: (orgId: string, data: Record<string, unknown>) => orgApi(orgId).post("/ai/draft-email", data),
  generateQuestions: (orgId: string, data: Record<string, unknown>) =>
    orgApi(orgId).post("/ai/generate-questions", data),
  fitAnalysis: (orgId: string, applicationId: string) =>
    orgApi(orgId).post("/ai/fit-analysis", { application_id: applicationId }),
  generateOfferLetter: (orgId: string, data: Record<string, unknown>) =>
    orgApi(orgId).post("/ai/generate-offer-letter", data),
};

// ─── Notifications ────────────────────────────────────────────────────────────

export const notificationsApi = {
  list: (orgId: string, params?: Record<string, unknown>) =>
    orgApi(orgId).get("/notifications", { params }),
  markRead: (orgId: string, notificationId: string) =>
    orgApi(orgId).post(`/notifications/${notificationId}/read`),
  markAllRead: (orgId: string) => orgApi(orgId).post("/notifications/read-all"),
};

// ─── Super Admin ──────────────────────────────────────────────────────────────

export const superAdminApi = {
  getStats: () => api.get("/superadmin/stats"),
  listOrgs: (params?: Record<string, unknown>) => api.get("/superadmin/organizations", { params }),
  getOrg: (orgId: string) => api.get(`/superadmin/organizations/${orgId}`),
  updateFeatureFlags: (orgId: string, flags: Record<string, boolean>) =>
    api.patch(`/superadmin/organizations/${orgId}/feature-flags`, { flags }),
  updateSeats: (orgId: string, maxSeats: number) =>
    api.patch(`/superadmin/organizations/${orgId}/seats`, { max_seats: maxSeats }),
  updateOrgStatus: (orgId: string, isActive: boolean) =>
    api.patch(`/superadmin/organizations/${orgId}/status`, { is_active: isActive }),
  listUsers: (params?: Record<string, unknown>) => api.get("/superadmin/users", { params }),
};
