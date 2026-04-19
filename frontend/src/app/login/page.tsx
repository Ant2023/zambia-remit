"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { formatApiError, loginCustomer, registerCustomer } from "@/lib/api";
import { saveAuthSession } from "@/lib/auth";

type AuthMode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
              first_name: String(form.get("first_name") ?? ""),
              last_name: String(form.get("last_name") ?? ""),
            });

      saveAuthSession(session);
      router.push("/");
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
            Use a customer account to send money, fund transactions, and track
            transfer status.
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
          {mode === "register" ? (
            <div className="form-grid">
              <label>
                First name
                <input name="first_name" required />
              </label>
              <label>
                Last name
                <input name="last_name" required />
              </label>
            </div>
          ) : null}

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
