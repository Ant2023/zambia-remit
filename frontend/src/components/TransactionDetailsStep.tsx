"use client";

import { FormEvent, useMemo, useState } from "react";
import type { Quote, RateEstimate, Recipient } from "@/lib/api";
import { createQuote, formatApiError } from "@/lib/api";

type TransactionDetailsStepProps = {
  authToken?: string;
  rateEstimate?: RateEstimate;
  recipient?: Recipient;
  payoutMethod: "mobile_money" | "bank_deposit";
  sendAmount: string;
  exchangeRate: string;
  estimatedReceiveAmount: string;
  reasonForSending: string;
  providerName: string;
  quote?: Quote;
  onCreated: (quote: Quote) => void;
};

export function TransactionDetailsStep({
  authToken,
  rateEstimate,
  recipient,
  payoutMethod,
  sendAmount,
  exchangeRate,
  estimatedReceiveAmount,
  reasonForSending,
  providerName,
  quote,
  onCreated,
}: TransactionDetailsStepProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const totalAmount = useMemo(() => {
    if (!quote) {
      return rateEstimate?.total_amount ?? "";
    }

    return (Number(quote.send_amount) + Number(quote.fee_amount)).toFixed(2);
  }, [quote, rateEstimate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authToken) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!rateEstimate || !recipient) {
      setError("Choose countries and complete recipient details first.");
      return;
    }

    if (!sendAmount || Number(sendAmount) <= 0) {
      setError("Enter the amount to send in Step 1.");
      return;
    }

    setLoading(true);

    try {
      const createdQuote = await createQuote(
        {
          corridor_id: rateEstimate.corridor_id,
          recipient_id: recipient.id,
          payout_method: payoutMethod,
          send_amount: sendAmount,
        },
        authToken,
      );
      onCreated(createdQuote);
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
          <h2>Transaction details</h2>
          <p className="muted small">Review the amount and recipient information.</p>
        </div>
      </div>

      <form className="stack" onSubmit={handleSubmit}>
        <dl className="summary-list">
          <div>
            <dt>Send amount</dt>
            <dd>
              {sendAmount || "Pending"} {rateEstimate?.source_currency.code ?? ""}
            </dd>
          </div>
          <div>
            <dt>Exchange rate</dt>
            <dd>
              {exchangeRate && rateEstimate
                ? `1 ${rateEstimate.source_currency.code} = ${exchangeRate} ${rateEstimate.destination_currency.code}`
                : "Pending"}
            </dd>
          </div>
          <div>
            <dt>Recipient receives</dt>
            <dd>
              {estimatedReceiveAmount || "Pending"}{" "}
              {rateEstimate?.destination_currency.code ?? ""}
            </dd>
          </div>
          <div>
            <dt>Total amount</dt>
            <dd>
              {totalAmount || "Pending"} {rateEstimate?.source_currency.code ?? ""}
            </dd>
          </div>
        </dl>

        {rateEstimate ? (
          <p className="notice small">
            Send between {rateEstimate.min_send_amount} and{" "}
            {rateEstimate.max_send_amount} {rateEstimate.source_currency.code}.
          </p>
        ) : null}

        {error ? <pre className="error small">{error}</pre> : null}

        <button
          type="submit"
          disabled={loading || !rateEstimate || !recipient || !authToken}
        >
          {loading ? "Preparing details..." : "Prepare transaction details"}
        </button>
      </form>

      {quote && recipient ? (
        <div className="review-box stack">
          <h3>Review before creating the transaction</h3>
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
              <dt>Recipient receives</dt>
              <dd>
                {quote.receive_amount} {quote.destination_currency.code}
              </dd>
            </div>
            <div>
              <dt>Total amount</dt>
              <dd>
                {totalAmount} {quote.source_currency.code}
              </dd>
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
              <dt>Recipient</dt>
              <dd>
                {recipient.first_name} {recipient.last_name}
              </dd>
            </div>
            <div>
              <dt>Recipient phone</dt>
              <dd>{recipient.phone_number}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </section>
  );
}
