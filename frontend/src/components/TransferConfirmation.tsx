"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Quote, Recipient } from "@/lib/api";
import { createTransfer, formatApiError } from "@/lib/api";

type TransferConfirmationProps = {
  authToken?: string;
  recipient?: Recipient;
  quote?: Quote;
  reasonForSending: string;
  providerName: string;
};

function formatPayoutMethod(value: Quote["payout_method"]) {
  return value === "mobile_money" ? "Mobile money" : "Bank deposit";
}

export function TransferConfirmation({
  authToken,
  recipient,
  quote,
  reasonForSending,
  providerName,
}: TransferConfirmationProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const totalAmount = useMemo(() => {
    if (!quote) {
      return "";
    }

    return (Number(quote.send_amount) + Number(quote.fee_amount)).toFixed(2);
  }, [quote]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authToken) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!recipient || !quote) {
      setError("Complete recipient details first so we can prepare your review.");
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
        <span className="step-number">3</span>
        <div>
          <h2>Review transaction</h2>
          <p className="muted small">
            Check the details before you send the money.
          </p>
        </div>
      </div>

      {quote && recipient ? (
        <div className="review-box stack">
          <dl className="summary-list">
            <div>
              <dt>Send amount</dt>
              <dd>
                {quote.send_amount} {quote.source_currency.code}
              </dd>
            </div>
            <div>
              <dt>Exchange rate</dt>
              <dd>
                1 {quote.source_currency.code} = {quote.exchange_rate}{" "}
                {quote.destination_currency.code}
              </dd>
            </div>
            <div>
              <dt>Fee</dt>
              <dd>
                {quote.fee_amount} {quote.source_currency.code}
              </dd>
            </div>
            <div>
              <dt>Total amount</dt>
              <dd>
                {totalAmount} {quote.source_currency.code}
              </dd>
            </div>
            <div>
              <dt>Recipient receives</dt>
              <dd>
                {quote.receive_amount} {quote.destination_currency.code}
              </dd>
            </div>
            <div>
              <dt>Recipient</dt>
              <dd>
                {recipient.first_name} {recipient.last_name}
              </dd>
            </div>
            <div>
              <dt>Payout method</dt>
              <dd>{formatPayoutMethod(quote.payout_method)}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{providerName || "Bank deposit"}</dd>
            </div>
            <div>
              <dt>Reason for sending</dt>
              <dd>{reasonForSending || "Not provided"}</dd>
            </div>
            <div>
              <dt>Destination country</dt>
              <dd>{quote.destination_country.name}</dd>
            </div>
          </dl>
        </div>
      ) : (
        <p className="muted small">
          Complete recipient details to prepare the transaction review.
        </p>
      )}

      <form className="stack" onSubmit={handleSubmit}>
        {error ? <pre className="error small">{error}</pre> : null}

        <button type="submit" disabled={loading || !recipient || !quote || !authToken}>
          {loading ? "Creating transaction..." : "Send money"}
        </button>
      </form>
    </section>
  );
}
