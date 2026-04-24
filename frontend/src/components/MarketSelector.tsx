"use client";

import type { Country, RateEstimate } from "@/lib/api";
import {
  getFxRateBadgeText,
  getFxRateSourceDescription,
} from "@/lib/fx";

type MarketSelectorProps = {
  senderCountries: Country[];
  destinationCountries: Country[];
  rateEstimate?: RateEstimate;
  sourceCountryId: string;
  destinationCountryId: string;
  sendAmount: string;
  exchangeRate: string;
  estimatedReceiveAmount: string;
  sourceCurrencyCode?: string;
  destinationCurrencyCode?: string;
  onSourceCountryChange: (value: string) => void;
  onDestinationCountryChange: (value: string) => void;
  onSendAmountChange: (value: string) => void;
};

export function MarketSelector({
  senderCountries,
  destinationCountries,
  rateEstimate,
  sourceCountryId,
  destinationCountryId,
  sendAmount,
  exchangeRate,
  estimatedReceiveAmount,
  sourceCurrencyCode,
  destinationCurrencyCode,
  onSourceCountryChange,
  onDestinationCountryChange,
  onSendAmountChange,
}: MarketSelectorProps) {
  const rateBadgeText = getFxRateBadgeText(rateEstimate);
  const rateSourceDescription = getFxRateSourceDescription(rateEstimate);

  return (
    <section className="panel stack">
      <div className="row">
        <span className="step-number">1</span>
        <div>
          <h2>Amount and countries</h2>
          <p className="muted small">Enter the amount and where the money is going.</p>
        </div>
      </div>

      <div className="form-grid">
        <label>
          Sender country
          <select
            value={sourceCountryId}
            onChange={(event) => onSourceCountryChange(event.target.value)}
          >
            <option value="">Select country</option>
            {senderCountries.map((country) => (
              <option key={country.id} value={country.id}>
                {country.name} ({country.currency.code})
              </option>
            ))}
          </select>
        </label>

        <label>
          Destination country
          <select
            value={destinationCountryId}
            onChange={(event) => onDestinationCountryChange(event.target.value)}
          >
            <option value="">Select country</option>
            {destinationCountries.map((country) => (
              <option key={country.id} value={country.id}>
                {country.name} ({country.currency.code})
              </option>
            ))}
          </select>
        </label>

        <label>
          Amount to send
          <input
            inputMode="decimal"
            placeholder="100.00"
            value={sendAmount}
            onChange={(event) => onSendAmountChange(event.target.value)}
          />
        </label>
      </div>

      <div className="rate-box">
        <span className="muted small">Exchange rate</span>
        <strong>
          {exchangeRate && sourceCurrencyCode && destinationCurrencyCode
            ? `1 ${sourceCurrencyCode} = ${exchangeRate} ${destinationCurrencyCode}`
            : "Select countries to see the rate"}
        </strong>
        <p className="muted small">
          {rateEstimate ? `${rateBadgeText}. ${rateSourceDescription}` : rateSourceDescription}
        </p>
      </div>

      <div className="rate-box">
        <span className="muted small">Recipient receives</span>
        <strong>
          {estimatedReceiveAmount && destinationCurrencyCode
            ? `${estimatedReceiveAmount} ${destinationCurrencyCode}`
            : "Enter an amount to calculate this"}
        </strong>
      </div>
    </section>
  );
}
