export const frontendConfig = {
  apiBaseUrl:
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
    "https://nexus-ai-trader-r2ez.onrender.com",
  apiAuthToken:
    (import.meta.env.VITE_API_AUTH_TOKEN as string | undefined) ??
    "nexus_sec_admin_7f9b8a3e4c1d2e5a6f8b",
} as const;

