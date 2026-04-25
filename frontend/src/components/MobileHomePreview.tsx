import type { SVGProps } from "react";
import type { Country } from "@/lib/api";

type MobileHomePreviewProps = {
  onContinue: () => void;
  previewAmount: string;
  onPreviewAmountChange: (value: string) => void;
  senderCountries: Country[];
  destinationCountries: Country[];
  sourceCountryId: string;
  destinationCountryId: string;
  onSourceCountryChange: (value: string) => void;
  onDestinationCountryChange: (value: string) => void;
  selectedSourceCountry?: Country;
  selectedDestinationCountry?: Country;
  getFlagPath: (country?: Country) => string;
  previewRateBadgeText: string;
  exchangeRateText: string;
  receiveAmountText: string;
  feeText: string;
  totalText: string;
  rateMessage: string;
};

function isNumericText(value: string) {
  return /^\d[\d,.]*$/.test(value.trim());
}

export function MobileHomePreview({
  onContinue,
  previewAmount,
  onPreviewAmountChange,
  senderCountries,
  destinationCountries,
  sourceCountryId,
  destinationCountryId,
  onSourceCountryChange,
  onDestinationCountryChange,
  selectedSourceCountry,
  selectedDestinationCountry,
  getFlagPath,
  previewRateBadgeText,
  exchangeRateText,
  receiveAmountText,
  feeText,
  totalText,
  rateMessage,
}: MobileHomePreviewProps) {
  const receiveAmountClassName = isNumericText(receiveAmountText)
    ? "mobile-amount"
    : "mobile-amount mobile-amount-placeholder";
  const trustFlags = [
    { src: "/flags/us.svg", label: "United States" },
    { src: "/flags/zm.svg", label: "Zambia" },
    { src: "/flags/gb.svg", label: "United Kingdom" },
  ];

  return (
    <>
      <section className="mobile-home-hero">
        <div className="mobile-shell">
          <div className="mobile-hero-image" id="mobile-how-it-works">
            <img
              src="/images/family-mobile-transfer.jpg"
              alt=""
              aria-hidden="true"
              className="mobile-hero-photo"
            />
            <div className="mobile-trust-row">
              <div className="mobile-trust-left">
                <ShieldCheckIcon className="mobile-shield" />
                <span>Secure</span>
                <span className="dot">&bull;</span>
                <span>Fast</span>
                <span className="dot">&bull;</span>
                <span>Transparent</span>
              </div>

              <div className="mobile-flags">
                {trustFlags.map((flag) => (
                  <span className="mobile-flag-chip" key={flag.label} title={flag.label}>
                    <img src={flag.src} alt="" />
                  </span>
                ))}
                <span className="mobile-plus">+6</span>
              </div>
            </div>

            <div className="mobile-hero-overlay">
              <h1>Send money across borders</h1>
              <p>
                Fast, secure transfers for families, everyday support, and
                businesses.
              </p>
              <div className="mobile-hero-actions">
                <button
                  className="mobile-hero-button mobile-hero-button-solid"
                  type="button"
                  onClick={onContinue}
                >
                  Start a transfer
                </button>
                <a
                  className="mobile-hero-button mobile-hero-button-ghost"
                  href="#mobile-preview"
                >
                  View rates
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mobile-quote-section" id="mobile-preview">
        <div className="mobile-shell">
          <div className="mobile-transfer-card">
          <div className="mobile-card-section mobile-card-top">
            <div className="mobile-card-left">
              <div className="mobile-label-row">
                <div className="mobile-label">You send</div>
                <span className="mobile-edit-hint" aria-hidden="true">
                  <PencilIcon />
                </span>
              </div>
              <input
                className="mobile-amount mobile-send-amount mobile-amount-input"
                inputMode="decimal"
                aria-label="Amount to send"
                value={previewAmount}
                onChange={(event) => onPreviewAmountChange(event.target.value)}
              />
            </div>

            <div className="mobile-currency-pill">
              <img
                className="mobile-currency-flag"
                src={getFlagPath(selectedSourceCountry)}
                alt=""
              />
              <select
                className="mobile-currency-select"
                aria-label="Sender country"
                value={sourceCountryId}
                onChange={(event) => onSourceCountryChange(event.target.value)}
              >
                {senderCountries.map((country) => (
                  <option key={country.id} value={country.id}>
                    {country.currency.code}
                  </option>
                ))}
              </select>
              <ChevronDownIcon className="mobile-currency-chevron" />
            </div>
          </div>

          <div className="mobile-rate-row">
            <div className="mobile-rate-line" aria-hidden="true">
              <span className="line" />
              <span className="dot-circle" />
              <span className="line" />
            </div>

            <div className="mobile-rate-content">
              <div className="mobile-rate-top">
                <span className="rate-label">Exchange rate</span>
                <span className="rate-badge">{previewRateBadgeText}</span>
              </div>
              <div className="rate-value">{exchangeRateText}</div>
            </div>
          </div>

          <div className="mobile-card-section">
            <div className="mobile-card-left">
              <div className="mobile-label mobile-receive-label">They get</div>
              <div className={`${receiveAmountClassName} mobile-receive-amount`}>
                {receiveAmountText}
              </div>
            </div>

            <div className="mobile-currency-pill">
              <img
                className="mobile-currency-flag"
                src={getFlagPath(selectedDestinationCountry)}
                alt=""
              />
              <select
                className="mobile-currency-select"
                aria-label="Destination country"
                value={destinationCountryId}
                onChange={(event) => onDestinationCountryChange(event.target.value)}
              >
                {destinationCountries.map((country) => (
                  <option key={country.id} value={country.id}>
                    {country.currency.code}
                  </option>
                ))}
              </select>
              <ChevronDownIcon className="mobile-currency-chevron" />
            </div>
          </div>

          <button className="mobile-method-row" type="button" onClick={onContinue}>
            <div className="mobile-method-left">
              <div className="mobile-method-icon">
                <PhoneIcon />
              </div>
              <div>
                <div className="mobile-method-label">Receive method</div>
                <div className="mobile-method-value">Mobile Money</div>
              </div>
            </div>

            <ChevronRightIcon className="mobile-method-arrow" />
          </button>

          <div className="mobile-summary">
            <div className="mobile-summary-row">
              <span className="mobile-summary-key">
                <TagIcon className="mobile-summary-icon" />
                <span>Fee</span>
              </span>
              <strong>{feeText}</strong>
            </div>

            <div className="mobile-summary-row">
              <span className="mobile-summary-key">
                <ClockIcon className="mobile-summary-icon" />
                <span>Transfer time</span>
              </span>
              <strong className="green">Same day</strong>
            </div>

            <div className="mobile-summary-row">
              <span className="mobile-summary-key">
                <CalculatorIcon className="mobile-summary-icon" />
                <span>Total to pay</span>
              </span>
              <strong>{totalText}</strong>
            </div>
          </div>

          {rateMessage ? <p className="mobile-rate-message">{rateMessage}</p> : null}

          <button className="mobile-continue-btn" onClick={onContinue} type="button">
            Continue
          </button>
          </div>

          <div className="mobile-safe-note">
            <LockIcon className="lock" />
            <span>Your money is safe with MbongoPay</span>
          </div>
        </div>
      </section>
    </>
  );
}

function ShieldCheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M12 3l7 3.2v5.4c0 4.2-2.7 8-7 9.9-4.3-1.9-7-5.7-7-9.9V6.2L12 3z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M9.2 11.8l1.8 1.9 3.9-4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ChevronDownIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M5 7.5l5 5 5-5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function ChevronRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M7 5l6 5-6 5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function PencilIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M13.9 3.6a1.5 1.5 0 112.1 2.1l-8.2 8.2-3.3.8.8-3.3 8.6-8.2z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
      <path
        d="M12.3 5.2l2.5 2.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.6"
      />
    </svg>
  );
}

function PhoneIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect
        x="7"
        y="2.75"
        width="10"
        height="18.5"
        rx="3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M10.15 6.2h3.7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <rect
        x="9.2"
        y="8.15"
        width="5.6"
        height="7.2"
        rx="1.15"
        stroke="currentColor"
        strokeWidth="1.6"
        opacity="0.9"
      />
      <circle cx="12" cy="18.1" r="0.9" fill="currentColor" />
    </svg>
  );
}

function TagIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M3.75 12.25L11.8 4.2h6.45v6.45l-8.05 8.05a2 2 0 01-2.83 0l-3.62-3.62a2 2 0 010-2.83z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <circle cx="14.8" cy="7.7" r="1.2" fill="currentColor" />
    </svg>
  );
}

function ClockIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="12" cy="12" r="8.25" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 7.5v4.8l3 1.9"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function CalculatorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <rect
        x="5"
        y="3"
        width="14"
        height="18"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M8 7.5h8"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <path
        d="M8.2 11.5h.01M12 11.5h.01M15.8 11.5h.01M8.2 15.5h.01M12 15.5h.01M15.8 15.5h.01"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function LockIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path
        d="M7.75 10V8.25a4.25 4.25 0 118.5 0V10"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <rect
        x="5"
        y="10"
        width="14"
        height="10.5"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <circle cx="12" cy="15.25" r="1.1" fill="currentColor" />
    </svg>
  );
}
