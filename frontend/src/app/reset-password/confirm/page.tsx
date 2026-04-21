"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import { confirmPasswordReset, formatApiError } from "@/lib/api";

export default function ResetPasswordConfirmPage() {
  const [uid, setUid] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setUid(params.get("uid") ?? "");
    setToken(params.get("token") ?? "");
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    if (!uid || !token) {
      setError("This password reset link is missing required details.");
      return;
    }

    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const passwordConfirm = String(form.get("password_confirm") ?? "");

    setLoading(true);

    try {
      const response = await confirmPasswordReset({
        uid,
        token,
        password,
        password_confirm: passwordConfirm,
      });
      setMessage(response.detail);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  const hasLinkDetails = Boolean(uid && token);

  return (
    <>
      <AppNavbar />
      <main className="auth-page">
        <section className="auth-shell">
          <div className="auth-card auth-card-wide">
            <div className="auth-icon">FX</div>
            <p className="auth-eyebrow">Account recovery</p>
            <h1>Choose a new password</h1>
            <p className="auth-copy">
              Set a new password for your customer account. Existing logged-in
              sessions will be cleared.
            </p>

            {!hasLinkDetails ? (
              <p className="error small">
                This reset link is missing required details. Request a new link.
              </p>
            ) : null}

            {message ? (
              <div className="stack">
                <p className="success small">{message}</p>
                <Link className="auth-primary-action" href="/login?mode=login">
                  Log in with new password
                </Link>
              </div>
            ) : (
              <form className="auth-form" onSubmit={handleSubmit}>
                <label>
                  New password
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    required
                    disabled={!hasLinkDetails}
                  />
                </label>

                <label>
                  Confirm new password
                  <input
                    name="password_confirm"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    required
                    disabled={!hasLinkDetails}
                  />
                </label>

                {error ? <pre className="error small">{error}</pre> : null}

                <button
                  type="submit"
                  className="auth-submit-button"
                  disabled={loading || !hasLinkDetails}
                >
                  {loading ? "Saving..." : "Reset password"}
                </button>
              </form>
            )}

            <p className="auth-note">
              Need another link? <Link href="/forgot-password">Start again</Link>
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
