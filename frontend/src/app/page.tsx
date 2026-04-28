"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppNavbar } from "@/components/AppNavbar";
import { MobileHomePreview } from "@/components/MobileHomePreview";
import {
  type AuthSession,
  type Country,
  type Currency,
  type RateEstimate,
  getDestinationCountries,
  getRateEstimate,
  getSenderCountries,
} from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";

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

const DEFAULT_HOME_PREVIEW_RATE = 25.4;
const DEFAULT_HOME_PREVIEW_SOURCE_CURRENCY = "USD";
const DEFAULT_HOME_PREVIEW_DESTINATION_CURRENCY = "ZMW";
const DEFAULT_HOME_PREVIEW_FEE = 0;

const HOW_IT_WORKS_STEPS = [
  {
    label: "01",
    title: "Get your quote",
    copy: "See the rate, fee, and receive amount before you send.",
  },
  {
    label: "02",
    title: "Add recipient",
    copy: "Choose who receives the money and how they get paid.",
  },
  {
    label: "03",
    title: "Pay and track",
    copy: "Complete payment and follow the transfer to delivery.",
  },
];

const COVERAGE_MARKETS = [
  {
    country: "United States",
    countryCode: "US",
    flag: "/flags/us.svg",
    copy: "Send from the United States when your destination is available.",
  },
  {
    country: "United Kingdom",
    countryCode: "GB",
    flag: "/flags/gb.svg",
    copy: "Check rates and destination availability before starting.",
  },
  {
    country: "Germany",
    countryCode: "DE",
    flag: "/flags/de.svg",
    copy: "Use supported destinations with clear rates and fees.",
  },
  {
    country: "Canada",
    countryCode: "CA",
    flag: "/flags/ca.svg",
    copy: "Send from Canada when supported destinations are available.",
  },
  {
    country: "France",
    countryCode: "FR",
    flag: "/flags/fr.svg",
    copy: "Check available destinations and payout methods before you send.",
  },
  {
    country: "Zambia",
    countryCode: "ZM",
    flag: "/flags/zm.svg",
    copy: "Use Zambia where it is available in supported transfer flows.",
  },
  {
    country: "Kenya",
    countryCode: "KE",
    flag: "/flags/ke.svg",
    copy: "Choose Kenya when it appears in your available country options.",
  },
  {
    country: "Tanzania",
    countryCode: "TZ",
    flag: "/flags/tz.svg",
    copy: "Check transfer options and delivery methods for Tanzania.",
  },
  {
    country: "South Africa",
    countryCode: "ZA",
    flag: "/flags/za.svg",
    copy: "Review rates, fees, and available destinations before starting.",
  },
  {
    country: "Zimbabwe",
    countryCode: "ZW",
    flag: "/flags/zw.svg",
    copy: "Use supported transfer options as they become available.",
  },
  {
    country: "Namibia",
    countryCode: "NA",
    flag: "/flags/na.svg",
    copy: "Check country availability in the transfer flow before you send.",
  },
];

const HOME_FAQS = [
  {
    question: "How fast are transfers?",
    answer:
      "Mobile Money transfers are designed for same-day delivery once payment and required checks are complete.",
  },
  {
    question: "Can I see the fee before I pay?",
    answer:
      "Yes. The quote shows the exchange rate, fee, receive amount, and total to pay before you continue.",
  },
  {
    question: "Where can I send money right now?",
    answer:
      "Supported countries are shown in the transfer flow. MbongoPay is built to add more countries over time.",
  },
  {
    question: "What receive method is supported?",
    answer:
      "Available receive methods appear based on the selected destination. Mobile Money is supported where available.",
  },
];

function isFallbackCountryId(countryId: string) {
  return countryId.startsWith("preview-country-");
}

function parseAmountNumber(value?: string | null) {
  if (!value) {
    return null;
  }

  const normalizedValue = value.replaceAll(",", "").trim();
  if (!normalizedValue) {
    return null;
  }

  const parsedAmount = Number(normalizedValue);
  return Number.isFinite(parsedAmount) ? parsedAmount : null;
}

function areAmountsEquivalent(left?: string | null, right?: string | null) {
  const leftAmount = parseAmountNumber(left);
  const rightAmount = parseAmountNumber(right);

  if (leftAmount === null || rightAmount === null) {
    return leftAmount === rightAmount;
  }

  return Math.abs(leftAmount - rightAmount) < 0.0001;
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
  const [loadingPreviewRate, setLoadingPreviewRate] = useState(false);
  const [previewCountriesLoaded, setPreviewCountriesLoaded] = useState(false);
  const [hasPreviewInteraction, setHasPreviewInteraction] = useState(false);
  const previewAmountNumber = parseAmountNumber(previewAmount);
  const previewRequestAmount =
    previewAmountNumber !== null && previewAmountNumber > 0
      ? String(previewAmountNumber)
      : undefined;

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
        setRateEstimate(undefined);
      } finally {
        setPreviewCountriesLoaded(true);
      }
    }

    loadPreviewCountries();
  }, []);

  useEffect(() => {
    let ignoreResult = false;

    async function loadPreviewRate() {
      if (!hasPreviewInteraction) {
        setLoadingPreviewRate(false);
        return;
      }

      if (!sourceCountryId || !destinationCountryId) {
        setLoadingPreviewRate(false);
        return;
      }

      if (
        isFallbackCountryId(sourceCountryId) ||
        isFallbackCountryId(destinationCountryId)
      ) {
        setRateEstimate(undefined);
        setLoadingPreviewRate(false);
        return;
      }

      setRateMessage("");
      setLoadingPreviewRate(true);

      try {
        const estimate = await getRateEstimate({
          source_country_id: sourceCountryId,
          destination_country_id: destinationCountryId,
          send_amount: previewRequestAmount,
          payout_method: "mobile_money",
        });
        if (ignoreResult) {
          return;
        }
        setRateEstimate(estimate);
        if (estimate.is_primary_rate) {
          setRateMessage("");
        } else if (estimate.rate_source === "frankfurter") {
          setRateMessage(
            "Open Exchange live rate is unavailable. Showing a fallback live market rate.",
          );
        } else {
          setRateMessage(
            "Open Exchange live rate is unavailable. Showing the latest stored reference rate.",
          );
        }
      } catch (error) {
        if (ignoreResult) {
          return;
        }
        setRateEstimate(undefined);
        setRateMessage(
          "Live rate data is temporarily unavailable. Please try again shortly.",
        );
      } finally {
        if (!ignoreResult) {
          setLoadingPreviewRate(false);
        }
      }
    }

    loadPreviewRate();

    return () => {
      ignoreResult = true;
    };
  }, [
    destinationCountryId,
    hasPreviewInteraction,
    previewRequestAmount,
    sourceCountryId,
  ]);

  const selectedSourceCountry = senderCountries.find(
    (country) => country.id === sourceCountryId,
  );
  const selectedDestinationCountry = destinationCountries.find(
    (country) => country.id === destinationCountryId,
  );
  const isCurrentSelectionRateEstimate =
    rateEstimate?.source_country.id === sourceCountryId &&
    rateEstimate?.destination_country.id === destinationCountryId &&
    (previewRequestAmount
      ? areAmountsEquivalent(rateEstimate?.send_amount, previewRequestAmount)
      : rateEstimate?.send_amount === null);
  const activeRateEstimate = isCurrentSelectionRateEstimate ? rateEstimate : undefined;
  const selectedSourceCurrencyCode = selectedSourceCountry?.currency.code ?? "USD";
  const selectedDestinationCurrencyCode =
    selectedDestinationCountry?.currency.code ?? "ZMW";
  const shouldShowDefaultPreview =
    selectedSourceCurrencyCode === DEFAULT_HOME_PREVIEW_SOURCE_CURRENCY &&
    selectedDestinationCurrencyCode === DEFAULT_HOME_PREVIEW_DESTINATION_CURRENCY &&
    !hasPreviewInteraction;
  const defaultPreviewSendAmount = previewAmountNumber ?? 0;
  const defaultPreviewReceiveAmount =
    defaultPreviewSendAmount * DEFAULT_HOME_PREVIEW_RATE;
  const sourceCurrencyCode =
    activeRateEstimate?.source_currency.code ?? selectedSourceCurrencyCode;
  const destinationCurrencyCode =
    activeRateEstimate?.destination_currency.code ?? selectedDestinationCurrencyCode;
  const previewSelectionReady =
    previewCountriesLoaded &&
    Boolean(sourceCountryId) &&
    Boolean(destinationCountryId) &&
    !isFallbackCountryId(sourceCountryId) &&
    !isFallbackCountryId(destinationCountryId);
  const transferStartHref = authSession ? "/send" : "/start";

  function handlePreviewSendMoney() {
    window.sessionStorage.setItem("sendAmount", previewAmount);
    if (sourceCountryId) {
      window.sessionStorage.setItem("sourceCountryId", sourceCountryId);
    }
    if (destinationCountryId) {
      window.sessionStorage.setItem("destinationCountryId", destinationCountryId);
    }
    if (activeRateEstimate) {
      window.sessionStorage.setItem("rateEstimate", JSON.stringify(activeRateEstimate));
    } else {
      window.sessionStorage.removeItem("rateEstimate");
    }
    window.sessionStorage.setItem("sourceCurrencyCode", sourceCurrencyCode);
    window.sessionStorage.setItem(
      "destinationCountryName",
      selectedDestinationCountry?.name ?? "Zambia",
    );
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

  function formatMoneyValue(value?: string | null) {
    if (!value) {
      return loadingPreviewRate || !previewSelectionReady ? "..." : "Unavailable";
    }

    return formatCurrencyAmount(Number(value));
  }

  function formatRateValue(value?: string) {
    if (!value) {
      return loadingPreviewRate || !previewSelectionReady
        ? "Loading live rate..."
        : "Live rate unavailable";
    }

    return Number(value).toLocaleString("en-US", {
      maximumFractionDigits: 4,
      minimumFractionDigits: 2,
    });
  }

  const mapItems = [
    { src: "/flags/us.svg", label: "United States" },
    { src: "/flags/gb.svg", label: "United Kingdom" },
    { src: "/flags/de.svg", label: "Germany" },
    { src: "/flags/zm.svg", label: "Zambia" },
  ];
  const flagRibbonItems = [...mapItems, ...mapItems, ...mapItems];
  const previewRateBadgeText = activeRateEstimate
    ? activeRateEstimate.is_primary_rate
      ? "Live Open Exchange rate"
      : activeRateEstimate.is_live_rate
        ? "Fallback live rate"
        : "Reference rate"
    : "Live rate";
  const mobilePreviewRateBadgeText = "Best rate";
  const exchangeRateText = shouldShowDefaultPreview
    ? `1 ${sourceCurrencyCode} = ${formatRateValue(String(DEFAULT_HOME_PREVIEW_RATE))} ${destinationCurrencyCode}`
    : activeRateEstimate
      ? `1 ${sourceCurrencyCode} = ${formatRateValue(activeRateEstimate.exchange_rate)} ${destinationCurrencyCode}`
      : formatRateValue();
  const previewReceiveAmountText = shouldShowDefaultPreview
    ? formatCurrencyAmount(defaultPreviewReceiveAmount)
    : formatMoneyValue(activeRateEstimate?.receive_amount);
  const previewFeeText = `${shouldShowDefaultPreview ? formatCurrencyAmount(DEFAULT_HOME_PREVIEW_FEE) : formatMoneyValue(activeRateEstimate?.fee_amount)} ${sourceCurrencyCode}`;
  const previewTotalText = `${shouldShowDefaultPreview ? formatCurrencyAmount(defaultPreviewSendAmount + DEFAULT_HOME_PREVIEW_FEE) : formatMoneyValue(activeRateEstimate?.total_amount)} ${sourceCurrencyCode}`;

  function handlePreviewAmountChange(value: string) {
    setHasPreviewInteraction(true);
    setPreviewAmount(value);
  }

  function handleSourceCountryChange(value: string) {
    setHasPreviewInteraction(true);
    setSourceCountryId(value);
  }

  function handleDestinationCountryChange(value: string) {
    setHasPreviewInteraction(true);
    setDestinationCountryId(value);
  }

  return (
    <div className="premium-home">
      <AppNavbar flagRibbonItems={flagRibbonItems} variant="home" />

      <MobileHomePreview
        onContinue={handlePreviewSendMoney}
        previewAmount={previewAmount}
        onPreviewAmountChange={handlePreviewAmountChange}
        senderCountries={senderCountries}
        destinationCountries={destinationCountries}
        sourceCountryId={sourceCountryId}
        destinationCountryId={destinationCountryId}
        onSourceCountryChange={handleSourceCountryChange}
        onDestinationCountryChange={handleDestinationCountryChange}
        selectedSourceCountry={selectedSourceCountry}
        selectedDestinationCountry={selectedDestinationCountry}
        getFlagPath={getFlagPath}
        previewRateBadgeText={mobilePreviewRateBadgeText}
        exchangeRateText={exchangeRateText}
        receiveAmountText={previewReceiveAmountText}
        feeText={previewFeeText}
        totalText={previewTotalText}
        rateMessage={rateMessage}
      />

      <main>
        <section className="premium-hero desktop-home-shell">
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
                    onChange={(event) =>
                      handlePreviewAmountChange(event.target.value)
                    }
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
                      onChange={(event) =>
                        handleSourceCountryChange(event.target.value)
                      }
                    >
                      {senderCountries.map((country) => (
                        <option key={country.id} value={country.id}>
                          {country.currency.code}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="rate-connector">
                <span className="rate-dot" />
                <div>
                  <span className="rate-badge">{previewRateBadgeText}</span>
                  <strong>{exchangeRateText}</strong>
                </div>
              </div>

              <div className="rate-field">
                <label className="rate-field-label">They get</label>
                <div className="rate-field-control">
                  <div className="rate-receive-amount">
                    {previewReceiveAmountText}
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
                      onChange={(event) =>
                        handleDestinationCountryChange(event.target.value)
                      }
                    >
                      {destinationCountries.map((country) => (
                        <option key={country.id} value={country.id}>
                          {country.currency.code}
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
                  <dd>{previewFeeText}</dd>
                </div>
                <div>
                  <dt>Transfer time</dt>
                  <dd>Same day</dd>
                </div>
                <div>
                  <dt>Total to pay</dt>
                  <dd>{previewTotalText}</dd>
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

        <section className="how-it-works-section" id="how-it-works">
          <div className="how-it-works-inner">
            <div className="how-it-works-heading">
              <p>How it works</p>
              <h2>How money moves</h2>
              <span>
                A clear flow from live quote to recipient delivery.
              </span>
            </div>

            <div className="how-it-works-list" aria-label="How MbongoPay works">
              {HOW_IT_WORKS_STEPS.map((step) => (
                <article className="how-it-works-step" key={step.title}>
                  <span className="how-it-works-number">{step.label}</span>
                  <div>
                    <h3>{step.title}</h3>
                    <span>{step.copy}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="coverage-section" id="coverage">
          <div className="coverage-inner">
            <div className="homepage-section-heading">
              <p>Countries</p>
              <h2>Countries we cover</h2>
              <span>
                Start from a supported sending country, then choose from the
                available destinations and payout methods in the transfer flow.
              </span>
            </div>

            <div className="coverage-carousel">
              <div
                className="coverage-route-viewport"
                aria-label="Countries MbongoPay covers"
              >
                <div className="coverage-route-grid">
                  <div className="coverage-route-set">
                    {COVERAGE_MARKETS.map((market) => (
                      <article
                        className="coverage-route-card"
                        key={market.country}
                      >
                        <div className="coverage-route-flags">
                          <span>
                            <img src={market.flag} alt="" />
                          </span>
                          <strong>{market.countryCode}</strong>
                        </div>
                        <h3>{market.country}</h3>
                        <p>{market.copy}</p>
                      </article>
                    ))}
                  </div>

                  <div className="coverage-route-set" aria-hidden="true">
                    {COVERAGE_MARKETS.map((market) => (
                      <article
                        className="coverage-route-card"
                        key={`${market.country}-duplicate`}
                      >
                        <div className="coverage-route-flags">
                          <span>
                            <img src={market.flag} alt="" />
                          </span>
                          <strong>{market.countryCode}</strong>
                        </div>
                        <h3>{market.country}</h3>
                        <p>{market.copy}</p>
                      </article>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="home-faq-section" id="faq">
          <div className="home-faq-inner">
            <div className="homepage-section-heading">
              <p>FAQ</p>
              <h2>Helpful answers before you send</h2>
            </div>

            <div className="home-faq-list">
              {HOME_FAQS.map((item) => (
                <details className="home-faq-item" key={item.question}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
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
                <a href="#coverage">Countries</a>
                <a href="#preview">Rates</a>
                <Link href="/compliance">Security</Link>
              </div>
            </div>

            <div>
              <p className="footer-heading">Company</p>
              <div className="footer-links">
                <a href="#faq">FAQ</a>
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
