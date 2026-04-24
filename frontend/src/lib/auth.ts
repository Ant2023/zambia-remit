import type { AuthSession } from "@/lib/api";

const AUTH_SESSION_KEY = "mbongoPayCustomerSession";
const LEGACY_AUTH_SESSION_KEY = "zambiaRemitCustomerSession";
export const AUTH_SESSION_EVENT = "mbongoPayAuthSessionChanged";
const FLOW_SESSION_KEYS = [
  "latestTransfer",
  "createdRecipient",
  "createdQuote",
  "sendAmount",
  "sourceCountryId",
  "destinationCountryId",
  "payoutMethod",
  "reasonForSending",
  "providerName",
  "rateEstimate",
  "sourceCurrencyCode",
  "destinationCountryName",
];

export function getStoredAuthSession(): AuthSession | null {
  const rawSession =
    window.sessionStorage.getItem(AUTH_SESSION_KEY) ??
    window.sessionStorage.getItem(LEGACY_AUTH_SESSION_KEY);

  if (!rawSession) {
    return null;
  }

  try {
    const session = JSON.parse(rawSession) as AuthSession;
    if (!isValidAuthSession(session)) {
      clearAuthSession();
      return null;
    }

    window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
    window.sessionStorage.removeItem(LEGACY_AUTH_SESSION_KEY);
    return session;
  } catch {
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
    window.sessionStorage.removeItem(LEGACY_AUTH_SESSION_KEY);
    return null;
  }
}

export function isValidAuthSession(session: unknown): session is AuthSession {
  if (!session || typeof session !== "object") {
    return false;
  }

  const candidate = session as AuthSession;
  return Boolean(candidate.token && candidate.user?.email);
}

export function saveAuthSession(session: AuthSession) {
  window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
  window.sessionStorage.removeItem(LEGACY_AUTH_SESSION_KEY);
  notifyAuthSessionChanged();
}

export function clearTransferDraft() {
  FLOW_SESSION_KEYS.forEach((key) => window.sessionStorage.removeItem(key));
}

export function clearCustomerSessionOnly() {
  window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  window.sessionStorage.removeItem(LEGACY_AUTH_SESSION_KEY);
  notifyAuthSessionChanged();
}

export function clearAuthSession() {
  clearCustomerSessionOnly();
  clearTransferDraft();
}

function notifyAuthSessionChanged() {
  window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
}
