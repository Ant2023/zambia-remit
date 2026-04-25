"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import { formatApiError, requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();

    try {
      const response = await requestPasswordReset({ email });
      setMessage(response.detail);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <AppNavbar />
      <main className="auth-page">
        <section className="auth-shell">
          <div className="auth-card auth-card-wide">
            <p className="auth-eyebrow">Account recovery</p>
            <h1>Reset your password</h1>
            <p className="auth-copy">
              Enter the email for your customer account. If it exists, we will
              send a secure reset link.
            </p>

            <form className="auth-form" onSubmit={handleSubmit}>
              <label>
                Email
                <input name="email" type="email" autoComplete="email" required />
              </label>

              {error ? <pre className="error small">{error}</pre> : null}
              {message ? <p className="success small">{message}</p> : null}

              <button
                type="submit"
                className="auth-submit-button"
                disabled={loading}
              >
                {loading ? "Sending..." : "Send reset link"}
              </button>
            </form>

            <p className="auth-note">
              Remembered it? <Link href="/login?mode=login">Log in</Link>
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
