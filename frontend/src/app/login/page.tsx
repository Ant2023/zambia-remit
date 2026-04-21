"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import {
  formatApiError,
  getCurrentUser,
  loginCustomer,
  registerCustomer,
} from "@/lib/api";
import {
  clearCustomerSessionOnly,
  isValidAuthSession,
  saveAuthSession,
} from "@/lib/auth";

type AuthMode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [nextPath, setNextPath] = useState("/");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next");
    if (next?.startsWith("/") && !next.startsWith("//")) {
      setNextPath(next);
    }

    const requestedMode = params.get("mode");
    if (requestedMode === "login" || requestedMode === "register") {
      setMode(requestedMode);
    }

    clearCustomerSessionOnly();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");

    try {
      const session =
        mode === "login"
          ? await loginCustomer({ email, password })
          : await registerCustomer({
              email,
              password,
              password_confirm: String(form.get("password_confirm") ?? ""),
            });

      if (!isValidAuthSession(session)) {
        throw new Error("Login succeeded, but the session response was invalid.");
      }

      const user = await getCurrentUser(session.token);
      saveAuthSession({ token: session.token, user });
      router.push(nextPath);
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
          <div className="auth-icon">MP</div>
          <p className="auth-eyebrow">Customer access</p>
          <h1>{mode === "login" ? "Log in" : "Create account"}</h1>
          <p className="auth-copy">
            {mode === "login"
              ? "Use a customer account to send money, fund transactions, and track transfer status."
              : "Create your account with email and password, then continue to the send-money flow."}
          </p>

          <div className="auth-tabs">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              Log in
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              Create account
            </button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <label>
              Email
              <input name="email" type="email" autoComplete="email" required />
            </label>

            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                minLength={8}
                required
              />
            </label>

            {mode === "login" ? (
              <Link className="text-link small" href="/forgot-password">
                Forgot your password?
              </Link>
            ) : null}

            {mode === "register" ? (
              <label>
                Confirm password
                <input
                  name="password_confirm"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  required
                />
              </label>
            ) : null}

            {error ? <pre className="error small">{error}</pre> : null}

            <button
              type="submit"
              className="auth-submit-button"
              disabled={loading}
            >
              {loading
                ? "Please wait..."
                : mode === "login"
                  ? "Log in"
                  : "Create customer account"}
            </button>
          </form>

          <p className="auth-note">
            Staff and admin accounts can use the{" "}
            <Link href="/operations">operations console</Link>.
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
