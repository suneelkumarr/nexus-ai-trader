export const DEFAULT_API_BASE_URL = "https://nexus-ai-trader-r2ez.onrender.com";
export const API_BASE_URL_STORAGE_KEY = "nexus_api_base_url";

export const DEFAULT_API_AUTH_TOKEN = "nexus_sec_admin_7f9b8a3e4c1d2e5a6f8b";
export const AUTH_TOKEN_STORAGE_KEY = "nexus_api_auth_token";

/**
 * Retrieve the active API base URL.
 * Precedence:
 *  1. Operator override in browser localStorage ("nexus_api_base_url")
 *  2. Build-time environment variable (import.meta.env.VITE_API_BASE_URL)
 *  3. Localhost automatic detection when running dev frontend
 *  4. Production default URL (DEFAULT_API_BASE_URL)
 */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem(API_BASE_URL_STORAGE_KEY)?.trim();
      if (stored) {
        return stored;
      }
      // When developing locally on localhost/127.0.0.1 without env override, connect to local FastAPI
      const host = window.location.hostname;
      if (host === "localhost" || host === "127.0.0.1") {
        const envBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
        return envBase || "http://localhost:8000";
      }
    } catch {
      // LocalStorage access may be restricted
    }
  }

  const envUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (envUrl) {
    return envUrl;
  }

  return DEFAULT_API_BASE_URL;
}

/**
 * Persist custom backend API URL in browser localStorage.
 */
export function setApiBaseUrl(url: string): void {
  if (typeof window !== "undefined") {
    try {
      const trimmed = url.trim().replace(/\/+$/, "");
      if (!trimmed || trimmed === DEFAULT_API_BASE_URL) {
        localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
      } else {
        localStorage.setItem(API_BASE_URL_STORAGE_KEY, trimmed);
      }
    } catch {
      // LocalStorage access may be restricted
    }
  }
}

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
      // LocalStorage access may be restricted
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
    return getApiBaseUrl();
  },
  get apiAuthToken(): string {
    return getAuthToken();
  },
};
