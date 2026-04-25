"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import { getStoredAuthSession } from "@/lib/auth";

export default function StartPage() {
  const router = useRouter();
  const [checkingSession, setCheckingSession] = useState(true);
  const [sendAmount, setSendAmount] = useState("100");
  const [sourceCurrencyCode, setSourceCurrencyCode] = useState("USD");
  const [destinationCountryName, setDestinationCountryName] = useState("Zambia");

  useEffect(() => {
    const session = getStoredAuthSession();
    if (session) {
      router.replace("/send");
      return;
    }

    setSendAmount(window.sessionStorage.getItem("sendAmount") || "100");
    setSourceCurrencyCode(window.sessionStorage.getItem("sourceCurrencyCode") || "USD");
    setDestinationCountryName(
      window.sessionStorage.getItem("destinationCountryName") || "Zambia",
    );
    setCheckingSession(false);
  }, [router]);

  const numericSendAmount = Number(sendAmount);
  const displaySendAmount =
    Number.isFinite(numericSendAmount) && numericSendAmount > 0
      ? numericSendAmount
      : 100;

  return (
    <>
      <AppNavbar variant="home" />
      <main className="auth-page">
        <section className="auth-shell">
        <div className="auth-card">
          <p className="auth-eyebrow">Continue your transfer</p>
          <h1>Create your profile</h1>
          <p className="auth-copy">
            Create a customer account or sign in to continue securely.
          </p>

          <div className="auth-transfer-preview">
            <span>Your transfer</span>
            <strong>
              {displaySendAmount.toLocaleString("en-US", {
                maximumFractionDigits: 2,
              })}{" "}
              {sourceCurrencyCode} to {destinationCountryName}
            </strong>
          </div>

          {checkingSession ? (
            <p className="auth-muted">Checking your session...</p>
          ) : (
            <>
              <Link
                className="auth-primary-action"
                href="/login?mode=register&next=/send"
              >
                Create account
              </Link>

              <p className="auth-inline">
                Already have an account?{" "}
                <Link href="/login?mode=login&next=/send">Sign in</Link>
              </p>

              <div className="auth-divider">
                <span>or</span>
              </div>

              <Link
                className="auth-secondary-action"
                href="/login?mode=login&next=/send"
              >
                Log in to continue
              </Link>
            </>
          )}

          <p className="auth-note">
            Staff and admin accounts should use Django admin.
          </p>
        </div>

        <Link className="auth-back-link" href="/">
          Back to homepage
        </Link>
        </section>
      </main>
    </>
  );
}
