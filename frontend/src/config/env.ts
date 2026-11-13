export const DEFAULT_API_AUTH_TOKEN = "nexus_sec_admin_7f9b8a3e4c1d2e5a6f8b";
export const AUTH_TOKEN_STORAGE_KEY = "nexus_api_auth_token";

/**
 * Retrieve the active administrative authentication token.
 * Precedence:
 *  1. Operator override in browser localStorage ("nexus_api_auth_token")
 *  2. Build-time environment variable (import.meta.env.VITE_API_AUTH_TOKEN)
 *  3. Institutional default token (DEFAULT_API_AUTH_TOKEN)
 */
export function getAuthToken(): string {
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)?.trim();
      if (stored) {
        return stored;
      }
    } catch {
      // LocalStorage access may be restricted in sandboxed iframes
    }
  }

  const envToken = (import.meta.env.VITE_API_AUTH_TOKEN as string | undefined)?.trim();
  if (envToken) {
    return envToken;
  }

  return DEFAULT_API_AUTH_TOKEN;
}

/**
 * Persist or clear custom operator authentication token in browser localStorage.
 */
export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") {
    try {
      const trimmed = token.trim();
      if (!trimmed || trimmed === DEFAULT_API_AUTH_TOKEN) {
        localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      } else {
        localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, trimmed);
      }
    } catch {
      // LocalStorage access may be restricted
    }
  }
}

export const frontendConfig = {
  get apiBaseUrl(): string {
    return (
      (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
      "https://nexus-ai-trader-r2ez.onrender.com"
    );
  },
  get apiAuthToken(): string {
    return getAuthToken();
  },
};
