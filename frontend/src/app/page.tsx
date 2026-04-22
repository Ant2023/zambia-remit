"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type AuthSession,
  type Country,
  type Currency,
  type RateEstimate,
  getDestinationCountries,
  getRateEstimate,
  getSenderCountries,
  logoutCustomer,
} from "@/lib/api";
import { clearAuthSession, getStoredAuthSession } from "@/lib/auth";

const PREVIEW_CURRENCIES: Record<string, Currency> = {
  USD: {
    id: "preview-currency-usd",
    code: "USD",
    name: "US Dollar",
    minor_unit: 2,
  },
  GBP: {
    id: "preview-currency-gbp",
    code: "GBP",
    name: "British Pound",
    minor_unit: 2,
  },
  EUR: {
    id: "preview-currency-eur",
    code: "EUR",
    name: "Euro",
    minor_unit: 2,
  },
  ZMW: {
    id: "preview-currency-zmw",
    code: "ZMW",
    name: "Zambian Kwacha",
    minor_unit: 2,
  },
};

const FALLBACK_SENDER_COUNTRIES: Country[] = [
  {
    id: "preview-country-us",
    name: "United States",
    iso_code: "US",
    dialing_code: "+1",
    currency: PREVIEW_CURRENCIES.USD,
    is_sender_enabled: true,
    is_destination_enabled: false,
  },
  {
    id: "preview-country-gb",
    name: "United Kingdom",
    iso_code: "GB",
    dialing_code: "+44",
    currency: PREVIEW_CURRENCIES.GBP,
    is_sender_enabled: true,
    is_destination_enabled: false,
  },
  {
    id: "preview-country-de",
    name: "Germany",
    iso_code: "DE",
    dialing_code: "+49",
    currency: PREVIEW_CURRENCIES.EUR,
    is_sender_enabled: true,
    is_destination_enabled: false,
  },
];

const FALLBACK_DESTINATION_COUNTRIES: Country[] = [
  {
    id: "preview-country-zm",
    name: "Zambia",
    iso_code: "ZM",
    dialing_code: "+260",
    currency: PREVIEW_CURRENCIES.ZMW,
    is_sender_enabled: false,
    is_destination_enabled: true,
  },
];

const FALLBACK_PREVIEW_RATES: Record<string, number> = {
  USD: 25.4,
  GBP: 32.25,
  EUR: 27.4,
};

function isFallbackCountryId(countryId: string) {
  return countryId.startsWith("preview-country-");
}

export default function Home() {
  const router = useRouter();
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [previewAmount, setPreviewAmount] = useState("100");
  const [senderCountries, setSenderCountries] = useState<Country[]>(
    FALLBACK_SENDER_COUNTRIES,
  );
  const [destinationCountries, setDestinationCountries] = useState<Country[]>(
    FALLBACK_DESTINATION_COUNTRIES,
  );
  const [sourceCountryId, setSourceCountryId] = useState(
    FALLBACK_SENDER_COUNTRIES[0].id,
  );
  const [destinationCountryId, setDestinationCountryId] = useState(
    FALLBACK_DESTINATION_COUNTRIES[0].id,
  );
  const [rateEstimate, setRateEstimate] = useState<RateEstimate>();
  const [rateMessage, setRateMessage] = useState("");
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setAuthSession(getStoredAuthSession());
  }, []);

  useEffect(() => {
    async function loadPreviewCountries() {
      try {
        const [senders, destinations] = await Promise.all([
          getSenderCountries(),
          getDestinationCountries(),
        ]);

        const defaultSource =
          senders.find((country) => country.currency.code === "USD") ?? senders[0];
        const defaultDestination =
          destinations.find((country) => country.currency.code === "ZMW") ??
          destinations[0];

        setSenderCountries(senders);
        setDestinationCountries(destinations);
        setSourceCountryId(defaultSource?.id ?? "");
        setDestinationCountryId(defaultDestination?.id ?? "");
      } catch (error) {
        setRateMessage(
          "Live rate data is temporarily unavailable. Please try again shortly.",
        );
      }
    }

    loadPreviewCountries();
  }, []);

  useEffect(() => {
    async function loadPreviewRate() {
      if (!sourceCountryId || !destinationCountryId) {
        return;
      }

      if (
        isFallbackCountryId(sourceCountryId) ||
        isFallbackCountryId(destinationCountryId)
      ) {
        setRateEstimate(undefined);
        return;
      }

      setRateMessage("");

      try {
        const amount = Number(previewAmount);
        const estimate = await getRateEstimate({
          source_country_id: sourceCountryId,
          destination_country_id: destinationCountryId,
          send_amount: amount > 0 ? previewAmount : undefined,
          payout_method: "mobile_money",
        });
        setRateEstimate(estimate);
      } catch (error) {
        setRateEstimate(undefined);
        setRateMessage(
          "Live rate data is temporarily unavailable. Please try again shortly.",
        );
      }
    }

    loadPreviewRate();
  }, [destinationCountryId, previewAmount, sourceCountryId]);

  async function handleLogout() {
    if (authSession?.token) {
      try {
        await logoutCustomer(authSession.token);
      } catch {
        // The local session should still be cleared if the token is already invalid.
      }
    }

    clearAuthSession();
    setAuthSession(null);
    router.push("/login");
  }

  const selectedSourceCountry = senderCountries.find(
    (country) => country.id === sourceCountryId,
  );
  const selectedDestinationCountry = destinationCountries.find(
    (country) => country.id === destinationCountryId,
  );
  const previewSendAmount = Number(previewAmount) > 0 ? Number(previewAmount) : 0;
  const previewExchangeRate = Number(
    rateEstimate?.exchange_rate ??
      FALLBACK_PREVIEW_RATES[selectedSourceCountry?.currency.code ?? "USD"] ??
      FALLBACK_PREVIEW_RATES.USD,
  );
  const previewFee = Number(rateEstimate?.fee_amount ?? "0");
  const previewReceiveAmount = Number(
    rateEstimate?.receive_amount ?? previewSendAmount * previewExchangeRate,
  );
  const previewTotalToPay = Number(
    rateEstimate?.total_amount ?? previewSendAmount + previewFee,
  );
  const sourceCurrencyCode =
    rateEstimate?.source_currency.code ?? selectedSourceCountry?.currency.code ?? "USD";
  const destinationCurrencyCode =
    rateEstimate?.destination_currency.code ??
    selectedDestinationCountry?.currency.code ??
    "ZMW";
  const transferStartHref = authSession ? "/send" : "/start";

  function handlePreviewSendMoney() {
    window.sessionStorage.setItem("sendAmount", previewAmount);
    if (sourceCountryId) {
      window.sessionStorage.setItem("sourceCountryId", sourceCountryId);
    }
    if (destinationCountryId) {
      window.sessionStorage.setItem("destinationCountryId", destinationCountryId);
    }
    router.push(transferStartHref);
  }

  function getFlagPath(country?: Country) {
    const isoCode = country?.iso_code.toLowerCase();
    const flagCode = isoCode === "uk" ? "gb" : isoCode;
    return flagCode ? `/flags/${flagCode}.svg` : "/flags/us.svg";
  }

  function formatCurrencyAmount(value: number) {
    return Number.isFinite(value)
      ? value.toLocaleString("en-US", { maximumFractionDigits: 2 })
      : "0";
  }

  const mapItems = [
    { src: "/flags/us.svg", label: "United States" },
    { src: "/flags/gb.svg", label: "United Kingdom" },
    { src: "/flags/de.svg", label: "Germany" },
    { src: "/flags/zm.svg", label: "Zambia" },
  ];
  const flagRibbonItems = [...mapItems, ...mapItems, ...mapItems];

  return (
    <div className="premium-home">
      <header className="premium-nav">
        <div className="premium-nav-inner">
          <Link className="premium-brand" href="/">
            <span className="brand-mark">MP</span>
            <span>
              <span className="brand-name">MbongoPay</span>
              <span className="brand-subtitle">Cross-border money transfers</span>
            </span>
          </Link>

          <nav className="premium-links" aria-label="Primary navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#preview">Rates</a>
            <a href="#trust">Security</a>
            <Link href="/help">Help</Link>
          </nav>

          <div className="premium-actions">
            {authSession ? (
              <>
                <span className="signed-in-label">{authSession.user.email}</span>
                <button
                  type="button"
                  className="nav-button ghost"
                  onClick={handleLogout}
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link className="nav-button ghost" href="/login?mode=login&next=/send">
                  Log in
                </Link>
                <Link className="nav-button solid" href={transferStartHref}>
                  Get started
                </Link>
              </>
            )}
          </div>

          <button
            type="button"
            className="mobile-menu-button"
            aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={isMobileMenuOpen}
            onClick={() => setIsMobileMenuOpen((isOpen) => !isOpen)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>

        {isMobileMenuOpen ? (
          <div className="premium-mobile-menu">
            <a href="#how-it-works" onClick={() => setIsMobileMenuOpen(false)}>
              How it works
            </a>
            <a href="#preview" onClick={() => setIsMobileMenuOpen(false)}>
              Rates
            </a>
            <a href="#trust" onClick={() => setIsMobileMenuOpen(false)}>
              Security
            </a>
            <Link href="/help" onClick={() => setIsMobileMenuOpen(false)}>
              Help
            </Link>
            {authSession ? (
              <button type="button" onClick={handleLogout}>
                Log out
              </button>
            ) : (
              <Link
                href="/login?mode=login&next=/send"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                Log in
              </Link>
            )}
          </div>
        ) : null}

        <div className="country-flag-ribbon" aria-hidden="true">
          <div className="country-flag-track">
            {flagRibbonItems.map((item, index) => (
              <div className="country-flag-chip" key={`${item.label}-${index}`}>
                <img src={item.src} alt="" />
              </div>
            ))}
          </div>
        </div>
      </header>

      <main>
        <section className="premium-hero">
          <div>
            <div className="premium-pill">
              Secure transfers for modern global payments
            </div>

            <h1>Send money across borders with confidence</h1>
            <p className="lede">
              Fast, transparent, and secure international transfers for families,
              everyday support, and business payments.
            </p>

            <div className="hero-buttons">
              <Link className="hero-button solid" href={transferStartHref}>
                Start a transfer
              </Link>
              <a className="hero-button ghost" href="#preview">
                View rates
              </a>
            </div>

            <span id="how-it-works" className="hero-anchor" aria-hidden="true" />
          </div>

          <div className="transfer-card preview-card" id="preview">
            <div className="preview-stack rate-check-stack">
              <div className="rate-field">
                <label className="rate-field-label">You send</label>
                <div className="rate-field-control">
                  <input
                    className="rate-amount-input"
                    inputMode="decimal"
                    aria-label="Amount to send"
                    value={previewAmount}
                    onChange={(event) => setPreviewAmount(event.target.value)}
                  />
                  <div className="rate-currency-select">
                    <img
                      className="currency-flag-image"
                      src={getFlagPath(selectedSourceCountry)}
                      alt=""
                    />
                    <select
                      className="rate-country-select"
                      aria-label="Sender country"
                      value={sourceCountryId}
                      onChange={(event) => setSourceCountryId(event.target.value)}
                    >
                      {senderCountries.map((country) => (
                        <option key={country.id} value={country.id}>
                          {country.currency.code} - {country.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="rate-connector">
                <span className="rate-dot" />
                <div>
                  <span className="rate-badge">First transfer rate</span>
                  <strong>
                    1 {sourceCurrencyCode} = {previewExchangeRate.toFixed(2)}{" "}
                    {destinationCurrencyCode}
                  </strong>
                </div>
              </div>

              <div className="rate-field">
                <label className="rate-field-label">They get</label>
                <div className="rate-field-control">
                  <div className="rate-receive-amount">
                    {formatCurrencyAmount(previewReceiveAmount)}
                  </div>
                  <div className="rate-currency-select">
                    <img
                      className="currency-flag-image"
                      src={getFlagPath(selectedDestinationCountry)}
                      alt=""
                    />
                    <select
                      className="rate-country-select"
                      aria-label="Destination country"
                      value={destinationCountryId}
                      onChange={(event) => setDestinationCountryId(event.target.value)}
                    >
                      {destinationCountries.map((country) => (
                        <option key={country.id} value={country.id}>
                          {country.currency.code} - {country.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="receive-method-field">
                <span>Receive method</span>
                <strong>Mobile Money</strong>
              </div>

              <dl className="rate-summary-list">
                <div>
                  <dt>Fee</dt>
                  <dd>
                    {previewFee.toFixed(2)} {sourceCurrencyCode}
                  </dd>
                </div>
                <div>
                  <dt>Transfer time</dt>
                  <dd>Same day</dd>
                </div>
                <div>
                  <dt>Total to pay</dt>
                  <dd>
                    {previewTotalToPay.toFixed(2)} {sourceCurrencyCode}
                  </dd>
                </div>
              </dl>

              {rateMessage ? <p className="rate-message">{rateMessage}</p> : null}

              <button
                type="button"
                className="preview-continue"
                onClick={handlePreviewSendMoney}
              >
                Continue
              </button>
            </div>
          </div>
        </section>

        <section className="trust-section" id="trust">
          <div className="trust-panel">
            <div className="trust-grid">
              <div className="trust-card">
                <p>Security</p>
                <h3>Protected every step of the way</h3>
                <span>
                  Built with verification, visibility, and transaction confidence at
                  the core.
                </span>
              </div>

              <div className="trust-card">
                <p>Clarity</p>
                <h3>Know what you send</h3>
                <span>
                  Clear rates, visible fees, and a smoother transfer experience from
                  start to finish.
                </span>
              </div>

              <div className="trust-card">
                <p>Convenience</p>
                <h3>Designed for real life</h3>
                <span>
                  Send for family support, urgent needs, everyday payments, and
                  business use.
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <div className="footer-cta-row">
            <div>
              <Link className="premium-brand footer-brand" href="/">
                <span className="brand-mark">MP</span>
                <span>
                  <span className="brand-name">MbongoPay</span>
                  <span className="brand-subtitle">
                    Cross-border money transfers
                  </span>
                </span>
              </Link>
              <p className="footer-description">
                Fast, secure, and modern money transfers designed for real life.
              </p>
            </div>

            <div className="footer-cta">
              <p>Ready to send?</p>
              <Link href={transferStartHref}>Start a transfer</Link>
            </div>
          </div>

          <div className="premium-footer-grid">
            <div>
              <p className="footer-heading">Product</p>
              <div className="footer-links">
                <a href="#how-it-works">How it works</a>
                <a href="#preview">Rates</a>
                <a href="#trust">Security</a>
              </div>
            </div>

            <div>
              <p className="footer-heading">Company</p>
              <div className="footer-links">
                <a href="#trust">About</a>
                <Link href="/help">Support</Link>
                <Link href="/contact">Contact</Link>
              </div>
            </div>

            <div>
              <p className="footer-heading">Legal</p>
              <div className="footer-links">
                <Link href="/privacy">Privacy Policy</Link>
                <Link href="/terms">Terms of Service</Link>
                <Link href="/refund-policy">Refund Policy</Link>
                <Link href="/compliance">Compliance</Link>
              </div>
            </div>
          </div>

          <div className="footer-bottom">
            <p>&copy; 2026 MbongoPay. All rights reserved.</p>
            <p>
              Modern cross-border payments with clarity, security, and confidence.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
