import type { AuthSession } from "@/lib/api";

const AUTH_SESSION_KEY = "zambiaRemitCustomerSession";

export function getStoredAuthSession(): AuthSession | null {
  const rawSession = window.sessionStorage.getItem(AUTH_SESSION_KEY);

  if (!rawSession) {
    return null;
  }

  try {
    return JSON.parse(rawSession) as AuthSession;
  } catch {
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
    return null;
  }
}

export function saveAuthSession(session: AuthSession) {
  window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export function clearAuthSession() {
  window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  window.sessionStorage.removeItem("latestTransfer");
  window.sessionStorage.removeItem("createdRecipient");
  window.sessionStorage.removeItem("createdQuote");
}
