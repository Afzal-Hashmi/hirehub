/**
 * Zustand global store — persists auth + current org selection.
 * The current org is sent as x-organization-id header on every API call.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface OrgSummary {
  organization_id: string;
  organization_name: string;
  organization_slug: string;
  organization_logo: string | null;
  role: string;
}

interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  global_role: string;
  organizations: OrgSummary[];
}

interface AuthStore {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  currentOrgId: string | null;

  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  setCurrentOrg: (orgId: string) => void;
  logout: () => void;

  get currentOrg(): OrgSummary | null;
  get isSuperAdmin(): boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      currentOrgId: null,

      setAuth: (user, accessToken, refreshToken) => {
        localStorage.setItem("hirehub_access_token", accessToken);
        localStorage.setItem("hirehub_refresh_token", refreshToken);
        const currentOrgId = user.organizations[0]?.organization_id ?? null;
        set({ user, accessToken, refreshToken, currentOrgId });
      },

      setCurrentOrg: (orgId) => set({ currentOrgId: orgId }),

      logout: () => {
        localStorage.removeItem("hirehub_access_token");
        localStorage.removeItem("hirehub_refresh_token");
        set({ user: null, accessToken: null, refreshToken: null, currentOrgId: null });
      },

      get currentOrg() {
        const { user, currentOrgId } = get();
        return user?.organizations.find((o) => o.organization_id === currentOrgId) ?? null;
      },

      get isSuperAdmin() {
        return get().user?.global_role === "super_admin";
      },
    }),
    {
      name: "hirehub-auth",
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        currentOrgId: state.currentOrgId,
      }),
    }
  )
);

// Feature flags store — loaded once per org switch
interface FeatureFlagsStore {
  flags: Record<string, boolean>;
  orgId: string | null;
  setFlags: (orgId: string, flags: Record<string, boolean>) => void;
  hasFlag: (flag: string) => boolean;
}

export const useFeatureFlagsStore = create<FeatureFlagsStore>()((set, get) => ({
  flags: {},
  orgId: null,
  setFlags: (orgId, flags) => set({ orgId, flags }),
  hasFlag: (flag) => get().flags[flag] ?? false,
}));
