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

const DEFAULT_PUBLIC_FLAG_RIBBON_ITEMS = [
  { src: "/flags/us.svg", label: "United States" },
  { src: "/flags/gb.svg", label: "United Kingdom" },
  { src: "/flags/de.svg", label: "Germany" },
  { src: "/flags/zm.svg", label: "Zambia" },
  { src: "/flags/us.svg", label: "United States" },
  { src: "/flags/gb.svg", label: "United Kingdom" },
  { src: "/flags/de.svg", label: "Germany" },
  { src: "/flags/zm.svg", label: "Zambia" },
  { src: "/flags/us.svg", label: "United States" },
  { src: "/flags/gb.svg", label: "United Kingdom" },
  { src: "/flags/de.svg", label: "Germany" },
  { src: "/flags/zm.svg", label: "Zambia" },
];

type AppNavbarProps = {
  flagRibbonItems?: Array<{
    label: string;
    src: string;
  }>;
  publicOnly?: boolean;
  variant?: "app" | "home";
};

export function AppNavbar({
  flagRibbonItems,
  publicOnly = false,
  variant = "app",
}: AppNavbarProps) {
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

  const visibleAuthSession = publicOnly ? null : authSession;
  const isStaff = Boolean(visibleAuthSession?.user.is_staff);
  const startHref = isStaff ? "/operations" : visibleAuthSession ? "/send?new=1" : "/start";
  const transferStartHref = visibleAuthSession ? "/send" : "/start";
  const isHomeVariant = variant === "home";
  const accountLabel = isHomeVariant
    ? visibleAuthSession?.user.email || getAccountLabel(visibleAuthSession)
    : getAccountLabel(visibleAuthSession);
  const publicAnchorPrefix = flagRibbonItems ? "" : "/";
  const renderedFlagRibbonItems = isHomeVariant
    ? (flagRibbonItems ?? DEFAULT_PUBLIC_FLAG_RIBBON_ITEMS)
    : flagRibbonItems;

  return (
    <header
      className={[
        "premium-nav",
        isHomeVariant ? "premium-nav-home" : "",
        isMobileMenuOpen ? "premium-nav-open" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="premium-nav-inner">
        <Link className="premium-brand" href="/">
          <span className="brand-mark">MP</span>
          <span>
            <span className="brand-name">MbongoPay</span>
            <span className="brand-subtitle">Cross-border money transfers</span>
          </span>
        </Link>

        <nav className="premium-links" aria-label="Primary navigation">
          {isHomeVariant ? (
            <>
              <Link href={`${publicAnchorPrefix}#how-it-works`}>How it works</Link>
              <Link href={`${publicAnchorPrefix}#preview`}>Rates</Link>
              <Link href="/compliance">Security</Link>
              <Link href="/help">Help</Link>
            </>
          ) : (
            <>
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
              <Link href="/help">Help</Link>
            </>
          )}
        </nav>

        <div className="premium-actions">
          {visibleAuthSession ? (
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
              <Link className="nav-button solid" href={isHomeVariant ? transferStartHref : "/start"}>
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
          {!isHomeVariant ? (
            <div className="premium-mobile-menu-header">
              <Link
                className="premium-mobile-menu-brand"
                href="/"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                <span className="brand-mark">MP</span>
                <span>
                  <span className="brand-name">MbongoPay</span>
                  <span className="brand-subtitle">Cross-border money transfers</span>
                </span>
              </Link>
              <button
                type="button"
                className="premium-mobile-menu-close"
                aria-label="Close menu"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                <span />
                <span />
              </button>
            </div>
          ) : null}

          {isHomeVariant ? (
            <>
              <Link
                href={`${publicAnchorPrefix}#how-it-works`}
                onClick={() => setIsMobileMenuOpen(false)}
              >
                How it works
              </Link>
              <Link
                href={`${publicAnchorPrefix}#preview`}
                onClick={() => setIsMobileMenuOpen(false)}
              >
                Rates
              </Link>
              <Link href="/compliance" onClick={() => setIsMobileMenuOpen(false)}>
                Security
              </Link>
              <Link href="/help" onClick={() => setIsMobileMenuOpen(false)}>
                Help
              </Link>
            </>
          ) : (
            <>
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
              <Link href="/help" onClick={() => setIsMobileMenuOpen(false)}>
                Help
              </Link>
            </>
          )}
          {visibleAuthSession ? (
            <button type="button" onClick={handleLogout}>
              Log out
            </button>
          ) : (
            <div className={isHomeVariant ? undefined : "premium-mobile-menu-actions"}>
              <Link
                href="/login?mode=login&next=/send"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                Log in
              </Link>
              {isHomeVariant ? (
                <Link
                  className="premium-mobile-menu-signin"
                  href="/login?mode=login&next=/send"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  Sign up
                </Link>
              ) : null}
              {!isHomeVariant ? (
                <Link href="/start" onClick={() => setIsMobileMenuOpen(false)}>
                  Get started
                </Link>
              ) : null}
            </div>
          )}
        </div>
      ) : null}

      {renderedFlagRibbonItems ? (
        <div className="country-flag-ribbon" aria-hidden="true">
          <div className="country-flag-track">
            {renderedFlagRibbonItems.map((item, index) => (
              <div className="country-flag-chip" key={`${item.label}-${index}`}>
                <img src={item.src} alt="" />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </header>
  );
}
