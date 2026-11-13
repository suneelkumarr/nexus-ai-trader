export const frontendConfig = {
  apiBaseUrl:
    (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
    "https://nexus-ai-trader-r2ez.onrender.com",
  // Never embed a fallback credential in source control. The token must be
  // supplied at build time via VITE_API_AUTH_TOKEN for authenticated deployments.
  apiAuthToken: (import.meta.env.VITE_API_AUTH_TOKEN as string | undefined)?.trim() ?? "",
} as const;

