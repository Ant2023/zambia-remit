"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import {
  ApiError,
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

function isExistingAccountError(error: unknown) {
  if (!(error instanceof ApiError)) {
    return false;
  }

  const details = error.details;
  if (!details || typeof details !== "object" || Array.isArray(details)) {
    return false;
  }

  const emailError = (details as Record<string, unknown>).email;
  const errorText = Array.isArray(emailError)
    ? emailError.join(" ")
    : String(emailError ?? "");

  return /exists|already/i.test(errorText);
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [nextPath, setNextPath] = useState("/");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showExistingAccountPrompt, setShowExistingAccountPrompt] =
    useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showPasswordConfirm, setShowPasswordConfirm] = useState(false);

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
    setShowExistingAccountPrompt(false);
    setLoading(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    const passwordConfirm = String(form.get("password_confirm") ?? "");
    const firstName = String(form.get("first_name") ?? "").trim();
    const lastName = String(form.get("last_name") ?? "").trim();

    if (!email) {
      setError("Enter your email address.");
      setLoading(false);
      return;
    }

    if (!password) {
      setError("Enter your password.");
      setLoading(false);
      return;
    }

    if (mode === "register") {
      if (!firstName || !lastName) {
        setError("Enter your first and last name.");
        setLoading(false);
        return;
      }

      if (!passwordConfirm) {
        setError("Confirm your password.");
        setLoading(false);
        return;
      }

      if (password !== passwordConfirm) {
        setError("Passwords do not match.");
        setLoading(false);
        return;
      }

      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        setLoading(false);
        return;
      }
    }

    try {
      const session =
        mode === "login"
          ? await loginCustomer({ email, password })
          : await registerCustomer({
              email,
              password,
              password_confirm: passwordConfirm,
              first_name: firstName,
              last_name: lastName,
            });

      if (!isValidAuthSession(session)) {
        throw new Error("Login succeeded, but the session response was invalid.");
      }

      const user = await getCurrentUser(session.token);
      saveAuthSession({ token: session.token, user });
      router.push(nextPath);
    } catch (apiError) {
      if (mode === "register" && isExistingAccountError(apiError)) {
        setError("An account with this email already exists.");
        setShowExistingAccountPrompt(true);
      } else {
        setError(formatApiError(apiError));
      }
    } finally {
      setLoading(false);
    }
  }

  function switchToExistingAccountLogin() {
    setMode("login");
    setError("");
    setShowExistingAccountPrompt(false);
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

          <form className="auth-form" onSubmit={handleSubmit} noValidate>
            {mode === "register" ? (
              <div className="form-grid">
                <label>
                  First name
                  <input
                    name="first_name"
                    autoComplete="given-name"
                    required
                  />
                </label>

                <label>
                  Last name
                  <input
                    name="last_name"
                    autoComplete="family-name"
                    required
                  />
                </label>
              </div>
            ) : null}

            <label>
              Email
              <input name="email" type="email" autoComplete="email" required />
            </label>

            <label>
              Password
              <span className="password-field">
                <input
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  required
                />
                <button
                  type="button"
                  className="password-toggle"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((current) => !current)}
                >
                  <EyeIcon hidden={showPassword} />
                </button>
              </span>
            </label>

            {mode === "login" ? (
              <Link className="text-link small" href="/forgot-password">
                Forgot your password?
              </Link>
            ) : null}

            {mode === "register" ? (
              <label>
                Confirm password
                <span className="password-field">
                  <input
                    name="password_confirm"
                    type={showPasswordConfirm ? "text" : "password"}
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    aria-label={
                      showPasswordConfirm
                        ? "Hide password confirmation"
                        : "Show password confirmation"
                    }
                    aria-pressed={showPasswordConfirm}
                    onClick={() =>
                      setShowPasswordConfirm((current) => !current)
                    }
                  >
                    <EyeIcon hidden={showPasswordConfirm} />
                  </button>
                </span>
              </label>
            ) : null}

            {error ? <pre className="error small">{error}</pre> : null}

            {showExistingAccountPrompt ? (
              <div className="auth-existing-account">
                <p>Use your existing account to continue.</p>
                <button
                  type="button"
                  className="auth-secondary-action"
                  onClick={switchToExistingAccountLogin}
                >
                  Sign in to existing account
                </button>
              </div>
            ) : null}

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

function EyeIcon({ hidden }: { hidden: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
    >
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {hidden ? <path d="m4 4 16 16" /> : null}
    </svg>
  );
}
