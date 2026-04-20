"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  formatApiError,
  getCurrentUser,
  loginCustomer,
  registerCustomer,
} from "@/lib/api";
import { clearAuthSession, isValidAuthSession, saveAuthSession } from "@/lib/auth";

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

    clearAuthSession();
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
    <main className="success-page">
      <section className="success-card stack">
        <div>
          <p className="kicker">Customer access</p>
          <h1>{mode === "login" ? "Log in" : "Create account"}</h1>
          <p className="lede">
            {mode === "login"
              ? "Use a customer account to send money, fund transactions, and track transfer status."
              : "Create your account with email and password, then continue to the send-money flow."}
          </p>
        </div>

        <div className="row">
          <button
            type="button"
            className={mode === "login" ? undefined : "secondary-button"}
            onClick={() => setMode("login")}
          >
            Log in
          </button>
          <button
            type="button"
            className={mode === "register" ? undefined : "secondary-button"}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>

        <form className="stack" onSubmit={handleSubmit}>
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required />
          </label>

          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              required
            />
          </label>

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

          <button type="submit" disabled={loading}>
            {loading
              ? "Please wait..."
              : mode === "login"
                ? "Log in"
                : "Create customer account"}
          </button>
        </form>

        <Link className="text-link" href="/">
          Back to send money
        </Link>
      </section>
    </main>
  );
}
