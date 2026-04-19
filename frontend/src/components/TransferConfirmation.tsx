"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import type { Quote, Recipient } from "@/lib/api";
import { createTransfer, formatApiError } from "@/lib/api";

type TransferConfirmationProps = {
  authToken?: string;
  recipient?: Recipient;
  quote?: Quote;
  reasonForSending: string;
};

export function TransferConfirmation({
  authToken,
  recipient,
  quote,
  reasonForSending,
}: TransferConfirmationProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authToken) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!recipient || !quote) {
      setError("Review the transaction details first.");
      return;
    }

    setLoading(true);

    try {
      const transfer = await createTransfer(
        {
          quote_id: quote.id,
          recipient_id: recipient.id,
          reason_for_transfer: reasonForSending,
        },
        authToken,
      );
      window.sessionStorage.setItem("latestTransfer", JSON.stringify(transfer));
      router.push(`/funding?transferId=${transfer.id}`);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel stack">
      <div className="row">
        <span className="step-number">4</span>
        <div>
          <h2>Confirm transaction</h2>
          <p className="muted small">Confirm the details are correct.</p>
        </div>
      </div>

      {quote ? (
        <p className="success small">
          The transaction details are ready. Create the transaction when everything
          looks correct.
        </p>
      ) : (
        <p className="muted small">Review the transaction details first.</p>
      )}

      <form className="stack" onSubmit={handleSubmit}>
        {error ? <pre className="error small">{error}</pre> : null}

        <button type="submit" disabled={loading || !recipient || !quote || !authToken}>
          {loading ? "Creating transaction..." : "Create transaction"}
        </button>
      </form>
    </section>
  );
}
