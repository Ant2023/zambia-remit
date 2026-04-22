"use client";

import { FormEvent, useState } from "react";

const supportEmail =
  process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@mbongopay.com";

export function SupportForm() {
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);
    const topic = String(form.get("topic") ?? "Transfer support");
    const email = String(form.get("email") ?? "").trim();
    const reference = String(form.get("reference") ?? "").trim();
    const message = String(form.get("message") ?? "").trim();
    const subject = `MbongoPay support request: ${topic}`;
    const body = [
      `Topic: ${topic}`,
      `Account email: ${email}`,
      `Transfer reference: ${reference || "Not provided"}`,
      "",
      message,
    ].join("\n");

    window.location.href = `mailto:${supportEmail}?subject=${encodeURIComponent(
      subject,
    )}&body=${encodeURIComponent(body)}`;
    setSubmitted(true);
  }

  return (
    <form className="support-form" onSubmit={handleSubmit}>
      <label>
        Topic
        <select name="topic" defaultValue="Transfer status">
          <option>Transfer status</option>
          <option>Payment or receipt</option>
          <option>Payout issue</option>
          <option>Refund request</option>
          <option>Verification review</option>
          <option>Account access</option>
        </select>
      </label>

      <label>
        Account email
        <input name="email" type="email" autoComplete="email" required />
      </label>

      <label>
        Transfer reference
        <input name="reference" placeholder="TRF..." />
      </label>

      <label>
        Message
        <textarea
          name="message"
          minLength={12}
          rows={6}
          required
        />
      </label>

      <button type="submit">Continue with email</button>
      {submitted ? (
        <p className="success small">
          Your email app should open with the support details filled in.
        </p>
      ) : null}
    </form>
  );
}
