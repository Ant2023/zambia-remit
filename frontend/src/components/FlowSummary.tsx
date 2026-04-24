"use client";

import type { Quote, RateEstimate, Recipient } from "@/lib/api";
import { getFxRateSourceSummary } from "@/lib/fx";

type FlowSummaryProps = {
  rateEstimate?: RateEstimate;
  recipient?: Recipient;
  quote?: Quote;
  sendAmount: string;
  exchangeRate: string;
  estimatedReceiveAmount: string;
  reasonForSending: string;
  providerName: string;
};

export function FlowSummary({
  rateEstimate,
  recipient,
  quote,
  sendAmount,
  exchangeRate,
  estimatedReceiveAmount,
  reasonForSending,
  providerName,
}: FlowSummaryProps) {
  const activeFxSnapshot = quote ?? rateEstimate;
  const displayedExchangeRate = quote?.exchange_rate ?? exchangeRate;
  const countriesText = quote
    ? `${quote.source_country.name} to ${quote.destination_country.name}`
    : rateEstimate
      ? `${rateEstimate.source_country.name} to ${rateEstimate.destination_country.name}`
      : "Not selected";
  const sendAmountText = quote
    ? `${quote.send_amount} ${quote.source_currency.code}`
    : sendAmount
      ? `${sendAmount} ${rateEstimate?.source_currency.code ?? ""}`
      : "Pending";

  return (
    <aside className="panel stack">
      <div>
        <p className="kicker">Current transfer</p>
        <h2>Summary</h2>
      </div>

      <dl className="summary-list">
        <div>
          <dt>Countries</dt>
          <dd>{countriesText}</dd>
        </div>
        <div>
          <dt>Send amount</dt>
          <dd>{sendAmountText}</dd>
        </div>
        <div>
          <dt>Exchange rate</dt>
          <dd>{displayedExchangeRate || "Pending"}</dd>
        </div>
        <div>
          <dt>FX source</dt>
          <dd>{getFxRateSourceSummary(activeFxSnapshot)}</dd>
        </div>
        <div>
          <dt>Recipient</dt>
          <dd>
            {recipient ? `${recipient.first_name} ${recipient.last_name}` : "Not added"}
          </dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{providerName || "Pending"}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{reasonForSending || "Pending"}</dd>
        </div>
        <div>
          <dt>Recipient receives</dt>
          <dd>
            {quote
              ? `${quote.receive_amount} ${quote.destination_currency.code}`
              : estimatedReceiveAmount && rateEstimate
                ? `${estimatedReceiveAmount} ${rateEstimate.destination_currency.code}`
                : "Pending"}
          </dd>
        </div>
      </dl>
    </aside>
  );
}
