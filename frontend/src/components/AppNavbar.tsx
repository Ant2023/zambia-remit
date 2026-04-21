"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { AuthSession } from "@/lib/api";
import { getCurrentUser, logoutCustomer } from "@/lib/api";
import {
  AUTH_SESSION_EVENT,
  clearAuthSession,
  getStoredAuthSession,
  saveAuthSession,
} from "@/lib/auth";

function getAccountLabel(session: AuthSession | null) {
  const name = [session?.user.first_name, session?.user.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();

  return name || session?.user.email || "";
}

export function AppNavbar() {
  const router = useRouter();
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    let isMounted = true;

    function syncStoredSession() {
      const session = getStoredAuthSession();
      setAuthSession(session);
      return session;
    }

    async function refreshCurrentUser(session: AuthSession | null) {
      if (!session?.token) {
        return;
      }

      try {
        const user = await getCurrentUser(session.token);
        if (!isMounted) {
          return;
        }

        const refreshedSession = { token: session.token, user };
        setAuthSession(refreshedSession);

        if (getAccountLabel(refreshedSession) !== getAccountLabel(session)) {
          saveAuthSession(refreshedSession);
        }
      } catch {
        // Keep the navbar usable if the account refresh fails.
      }
    }

    const session = syncStoredSession();
    void refreshCurrentUser(session);

    function handleSessionChange() {
      syncStoredSession();
    }

    window.addEventListener(AUTH_SESSION_EVENT, handleSessionChange);
    window.addEventListener("storage", handleSessionChange);

    return () => {
      isMounted = false;
      window.removeEventListener(AUTH_SESSION_EVENT, handleSessionChange);
      window.removeEventListener("storage", handleSessionChange);
    };
  }, []);

  async function handleLogout() {
    if (authSession?.token) {
      try {
        await logoutCustomer(authSession.token);
      } catch {
        // Keep logout reliable even if the token has expired.
      }
    }

    clearAuthSession();
    setAuthSession(null);
    setIsMobileMenuOpen(false);
    router.push("/login?mode=login&next=/send");
  }

  const isStaff = Boolean(authSession?.user.is_staff);
  const startHref = isStaff ? "/operations" : authSession ? "/send?new=1" : "/start";
  const accountLabel = getAccountLabel(authSession);

  return (
    <header className="premium-nav">
      <div className="premium-nav-inner">
        <Link className="premium-brand" href="/">
          <span className="brand-mark">MP</span>
          <span>
            <span className="brand-name">MbongoPay</span>
            <span className="brand-subtitle">Cross-border money transfers</span>
          </span>
        </Link>

        <nav className="premium-links" aria-label="Primary navigation">
          <Link href="/">Home</Link>
          {isStaff ? (
            <Link href="/operations">Operations</Link>
          ) : (
            <>
              <Link href="/dashboard">Dashboard</Link>
              <Link href={startHref}>Send</Link>
              <Link href="/recipients">Recipients</Link>
              <Link href="/profile">Account</Link>
              <Link href="/history">History</Link>
            </>
          )}
          <Link href="/history">Help</Link>
        </nav>

        <div className="premium-actions">
          {authSession ? (
            <>
              <span className="signed-in-label">{accountLabel}</span>
              <button
                type="button"
                className="nav-button ghost"
                onClick={handleLogout}
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link
                className="nav-button ghost"
                href="/login?mode=login&next=/send"
              >
                Log in
              </Link>
              <Link className="nav-button solid" href="/start">
                Get started
              </Link>
            </>
          )}
        </div>

        <button
          type="button"
          className="mobile-menu-button"
          aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
          aria-expanded={isMobileMenuOpen}
          onClick={() => setIsMobileMenuOpen((isOpen) => !isOpen)}
        >
          <span />
          <span />
          <span />
        </button>
      </div>

      {isMobileMenuOpen ? (
        <div className="premium-mobile-menu">
          <Link href="/" onClick={() => setIsMobileMenuOpen(false)}>
            Home
          </Link>
          {isStaff ? (
            <Link href="/operations" onClick={() => setIsMobileMenuOpen(false)}>
              Operations
            </Link>
          ) : (
            <>
              <Link href="/dashboard" onClick={() => setIsMobileMenuOpen(false)}>
                Dashboard
              </Link>
              <Link href={startHref} onClick={() => setIsMobileMenuOpen(false)}>
                Send
              </Link>
              <Link href="/recipients" onClick={() => setIsMobileMenuOpen(false)}>
                Recipients
              </Link>
              <Link href="/profile" onClick={() => setIsMobileMenuOpen(false)}>
                Account
              </Link>
              <Link href="/history" onClick={() => setIsMobileMenuOpen(false)}>
                History
              </Link>
            </>
          )}
          <Link href="/history" onClick={() => setIsMobileMenuOpen(false)}>
            Help
          </Link>
          {authSession ? (
            <button type="button" onClick={handleLogout}>
              Log out
            </button>
          ) : (
            <Link
              href="/login?mode=login&next=/send"
              onClick={() => setIsMobileMenuOpen(false)}
            >
              Log in
            </Link>
          )}
        </div>
      ) : null}
    </header>
  );
}
