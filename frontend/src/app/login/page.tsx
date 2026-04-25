"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import { Button, Card, Input, MobileContainer, StatusBadge } from "@/components/ui";
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
      <AppNavbar variant="home" />
      <MobileContainer className="login-modern-shell max-w-[520px] space-y-5 py-6 sm:py-10">
        <div className="login-modern-form-column">
          <Card className="login-modern-card space-y-6">
          <div className="login-modern-heading space-y-4 text-center">
            <div className="login-modern-title-block space-y-2">
              <StatusBadge tone="info">
                {mode === "login" ? "Log in" : "Create account"}
              </StatusBadge>
              <p className="mx-auto max-w-sm text-sm leading-6 text-mbongo-muted">
                {mode === "login"
                  ? "Use your customer account to send money, fund transfers, and track delivery."
                  : "Create your secure account, then continue to the send-money flow."}
              </p>
            </div>
          </div>

          <div className="login-modern-tabs grid grid-cols-2 rounded-xl bg-mbongo-bg p-1">
            <Button
              data-active={mode === "login"}
              className={
                mode === "login"
                  ? "min-h-11 w-full bg-white text-mbongo-navy shadow-sm hover:bg-white"
                  : "min-h-11 w-full border-0 bg-transparent text-mbongo-muted hover:bg-white/70"
              }
              onClick={() => setMode("login")}
              type="button"
              variant="secondary"
            >
              Log in
            </Button>
            <Button
              data-active={mode === "register"}
              className={
                mode === "register"
                  ? "min-h-11 w-full bg-white text-mbongo-navy shadow-sm hover:bg-white"
                  : "min-h-11 w-full border-0 bg-transparent text-mbongo-muted hover:bg-white/70"
              }
              onClick={() => setMode("register")}
              type="button"
              variant="secondary"
            >
              Create account
            </Button>
          </div>

          <form className="login-modern-form" onSubmit={handleSubmit} noValidate>
            {mode === "register" ? (
              <div className="login-modern-name-grid">
                <Input
                  autoComplete="given-name"
                  label="First name"
                  name="first_name"
                  required
                />

                <Input
                  autoComplete="family-name"
                  label="Last name"
                  name="last_name"
                  required
                />
              </div>
            ) : null}

            <Input
              autoComplete="email"
              label="Email"
              name="email"
              required
              type="email"
            />

            <label className="mbp-label">
              <span>Password</span>
              <span className="login-modern-password-field">
                <Input
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  className="login-modern-password-input pr-12"
                  name="password"
                  required
                  type={showPassword ? "text" : "password"}
                />
                <button
                  type="button"
                  className="login-modern-password-toggle"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => setShowPassword((current) => !current)}
                >
                  <EyeIcon hidden={showPassword} />
                </button>
              </span>
            </label>

            {mode === "login" ? (
              <Link
                className="login-modern-link justify-self-start text-sm font-semibold text-mbongo-teal hover:text-mbongo-navy"
                href="/forgot-password"
              >
                Forgot your password?
              </Link>
            ) : null}

            {mode === "register" ? (
              <label className="mbp-label">
                <span>Confirm password</span>
                <span className="login-modern-password-field">
                  <Input
                    autoComplete="new-password"
                    className="login-modern-password-input pr-12"
                    name="password_confirm"
                    required
                    type={showPasswordConfirm ? "text" : "password"}
                  />
                  <button
                    type="button"
                    className="login-modern-password-toggle"
                    aria-label={
                      showPasswordConfirm
                        ? "Hide password confirmation"
                        : "Show password confirmation"
                    }
                    aria-pressed={showPasswordConfirm}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() =>
                      setShowPasswordConfirm((current) => !current)
                    }
                  >
                    <EyeIcon hidden={showPasswordConfirm} />
                  </button>
                </span>
              </label>
            ) : null}

            {error ? (
              <div className="login-modern-error">
                <pre className="whitespace-pre-wrap text-sm font-semibold leading-6 text-mbongo-error">
                  {error}
                </pre>
              </div>
            ) : null}

            {showExistingAccountPrompt ? (
              <div className="login-modern-prompt">
                <p className="text-sm font-semibold text-mbongo-navy">
                  Use your existing account to continue.
                </p>
                <Button
                  fullWidth
                  onClick={switchToExistingAccountLogin}
                  type="button"
                  variant="secondary"
                >
                  Sign in to existing account
                </Button>
              </div>
            ) : null}

            <Button disabled={loading} fullWidth size="lg" type="submit">
              {loading
                ? "Please wait..."
                : mode === "login"
                  ? "Log in"
                  : "Create customer account"}
            </Button>
          </form>

          <p className="login-modern-note text-center text-sm leading-6 text-mbongo-muted">
            Staff and admin accounts can use{" "}
            <Link
              className="login-modern-link font-semibold text-mbongo-teal hover:text-mbongo-navy"
              href="/operations"
            >
              operations console
            </Link>
            .
          </p>
        </Card>

        <div className="login-modern-support-strip">
          <span>Need help?</span>
          <Link className="login-modern-link" href="/help">
            Help Center
          </Link>
        </div>

        <Link
          className="login-modern-back block text-center text-sm font-semibold text-mbongo-teal hover:text-mbongo-navy"
          href="/"
        >
          Back to homepage
        </Link>
        </div>
      </MobileContainer>
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
