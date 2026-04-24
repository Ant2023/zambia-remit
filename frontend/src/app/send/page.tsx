"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppNavbar } from "@/components/AppNavbar";
import { FlowSummary } from "@/components/FlowSummary";
import { MarketSelector } from "@/components/MarketSelector";
import { RecipientForm } from "@/components/RecipientForm";
import { SavedRecipientSelector } from "@/components/SavedRecipientSelector";
import { TransferConfirmation } from "@/components/TransferConfirmation";
import {
  type AuthSession,
  type Country,
  type Quote,
  type RateEstimate,
  type Recipient,
  createQuote,
  formatApiError,
  getDestinationCountries,
  getRateEstimate,
  getRecipients,
  getSenderCountries,
} from "@/lib/api";
import {
  clearTransferDraft,
  getStoredAuthSession,
} from "@/lib/auth";
import type { PayoutMethod } from "@/lib/transfer-options";

type SendStep = "market" | "recipient" | "review";
type RecipientEntryMode = "saved" | "new";

function getRecipientName(recipient?: Recipient) {
  if (!recipient) {
    return "";
  }

  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

export default function SendPage() {
  const router = useRouter();
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [senderCountries, setSenderCountries] = useState<Country[]>([]);
  const [destinationCountries, setDestinationCountries] = useState<Country[]>([]);
  const [sourceCountryId, setSourceCountryId] = useState("");
  const [destinationCountryId, setDestinationCountryId] = useState("");
  const [sendAmount, setSendAmount] = useState("");
  const [rateEstimate, setRateEstimate] = useState<RateEstimate>();
  const [savedRecipients, setSavedRecipients] = useState<Recipient[]>([]);
  const [recipient, setRecipient] = useState<Recipient>();
  const [quote, setQuote] = useState<Quote>();
  const [payoutMethod, setPayoutMethod] =
    useState<PayoutMethod>("mobile_money");
  const [reasonForSending, setReasonForSending] = useState("");
  const [providerName, setProviderName] = useState("");
  const [loadingDiscovery, setLoadingDiscovery] = useState(true);
  const [loadingRecipients, setLoadingRecipients] = useState(false);
  const [loadingRate, setLoadingRate] = useState(false);
  const [error, setError] = useState("");
  const [rateError, setRateError] = useState("");
  const [flowKey, setFlowKey] = useState(0);
  const [activeStep, setActiveStep] = useState<SendStep>("market");
  const [recipientEntryMode, setRecipientEntryMode] =
    useState<RecipientEntryMode>("saved");

  useEffect(() => {
    const session = getStoredAuthSession();
    setAuthSession(session);

    if (!session) {
      router.replace("/start");
      return;
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1") {
      clearTransferDraft();
      resetFlowState();
      window.history.replaceState(null, "", "/send");
      return;
    }

    const savedRecipient = window.sessionStorage.getItem("createdRecipient");
    const savedQuote = window.sessionStorage.getItem("createdQuote");
    const savedRateEstimate = window.sessionStorage.getItem("rateEstimate");
    const savedSendAmount = window.sessionStorage.getItem("sendAmount") ?? "";
    const savedSourceCountryId = window.sessionStorage.getItem("sourceCountryId");
    const savedDestinationCountryId =
      window.sessionStorage.getItem("destinationCountryId");
    const savedPayoutMethod = window.sessionStorage.getItem("payoutMethod");
    const savedReason = window.sessionStorage.getItem("reasonForSending") ?? "";
    const savedProvider = window.sessionStorage.getItem("providerName") ?? "";

    const restoredRecipient = savedRecipient
      ? (JSON.parse(savedRecipient) as Recipient)
      : undefined;
    const restoredQuote = savedQuote ? (JSON.parse(savedQuote) as Quote) : undefined;
    const restoredRateEstimate = savedRateEstimate
      ? (JSON.parse(savedRateEstimate) as RateEstimate)
      : undefined;

    if (restoredRecipient) {
      setRecipient(restoredRecipient);
    }

    if (restoredQuote) {
      setQuote(restoredQuote);
    }

    if (restoredRateEstimate) {
      setRateEstimate(restoredRateEstimate);
    }

    if (restoredRecipient && restoredQuote) {
      setActiveStep("review");
    } else if (restoredRecipient) {
      setActiveStep("recipient");
    }

    if (savedPayoutMethod === "mobile_money" || savedPayoutMethod === "bank_deposit") {
      setPayoutMethod(savedPayoutMethod);
    }

    setSendAmount(savedSendAmount);
    setSourceCountryId(savedSourceCountryId ?? "");
    setDestinationCountryId(savedDestinationCountryId ?? "");
    setReasonForSending(savedReason);
    setProviderName(savedProvider);
  }, []);

  useEffect(() => {
    if (!authSession?.token) {
      setSavedRecipients([]);
      return;
    }

    loadSavedRecipients(authSession.token);
  }, [authSession?.token]);

  useEffect(() => {
    async function loadCountries() {
      setLoadingDiscovery(true);
      setError("");

      try {
        const [senders, destinations] = await Promise.all([
          getSenderCountries(),
          getDestinationCountries(),
        ]);

        setSenderCountries(senders);
        setDestinationCountries(destinations);

        const savedSourceCountryId = window.sessionStorage.getItem("sourceCountryId");
        const savedDestinationCountryId =
          window.sessionStorage.getItem("destinationCountryId");
        const defaultSource =
          senders.find((country) => country.id === savedSourceCountryId) ??
          senders[0];
        const defaultDestination =
          destinations.find((country) => country.id === savedDestinationCountryId) ??
          destinations[0];

        if (defaultSource) {
          setSourceCountryId(defaultSource.id);
        }

        if (defaultDestination) {
          setDestinationCountryId(defaultDestination.id);
        }
      } catch (apiError) {
        setError(formatApiError(apiError));
      } finally {
        setLoadingDiscovery(false);
      }
    }

    loadCountries();
  }, []);

  useEffect(() => {
    async function loadRate() {
      if (!sourceCountryId || !destinationCountryId) {
        setRateEstimate(undefined);
        return;
      }

      setLoadingRate(true);
      setRateError("");

      try {
        const amount = Number(sendAmount);
        const estimate = await getRateEstimate({
          source_country_id: sourceCountryId,
          destination_country_id: destinationCountryId,
          send_amount: amount > 0 ? sendAmount : undefined,
          payout_method: payoutMethod,
        });
        setRateEstimate(estimate);
        window.sessionStorage.setItem("rateEstimate", JSON.stringify(estimate));
      } catch (apiError) {
        setRateEstimate(undefined);
        window.sessionStorage.removeItem("rateEstimate");
        setRateError(formatApiError(apiError));
      } finally {
        setLoadingRate(false);
      }
    }

    loadRate();
  }, [destinationCountryId, payoutMethod, sendAmount, sourceCountryId]);

  const selectedDestinationCountry = destinationCountries.find(
    (country) => country.id === destinationCountryId,
  );
  const destinationSavedRecipients = selectedDestinationCountry
    ? savedRecipients.filter(
        (savedRecipient) =>
          savedRecipient.country.id === selectedDestinationCountry.id,
      )
    : [];
  const hasSavedRecipients = destinationSavedRecipients.length > 0;
  const savedRecipientOptionAvailable = hasSavedRecipients || loadingRecipients;
  const visibleRecipientEntryMode =
    savedRecipientOptionAvailable && recipientEntryMode === "saved"
      ? "saved"
      : "new";

  const exchangeRate = rateEstimate?.exchange_rate ?? "";
  const estimatedReceiveAmount = rateEstimate?.receive_amount ?? "";
  const isReadyForReview = Boolean(recipient && quote);
  const amountNumber = Number(sendAmount);
  const canContinueToRecipient =
    Boolean(sourceCountryId && destinationCountryId && rateEstimate) &&
    amountNumber > 0 &&
    !loadingRate &&
    !rateError;
  const sourceCountryName =
    rateEstimate?.source_country.name ??
    senderCountries.find((country) => country.id === sourceCountryId)?.name ??
    "Sender country";
  const destinationCountryName =
    selectedDestinationCountry?.name ??
    rateEstimate?.destination_country.name ??
    "Destination country";
  const sourceCurrencyCode =
    rateEstimate?.source_currency.code ??
    senderCountries.find((country) => country.id === sourceCountryId)?.currency.code ??
    "";
  const destinationCurrencyCode =
    rateEstimate?.destination_currency.code ??
    selectedDestinationCountry?.currency.code ??
    "";
  const recipientName = getRecipientName(recipient);

  useEffect(() => {
    if (activeStep !== "recipient") {
      return;
    }

    if (loadingRecipients) {
      return;
    }

    setRecipientEntryMode(hasSavedRecipients ? "saved" : "new");
  }, [activeStep, destinationCountryId, hasSavedRecipients, loadingRecipients]);

  function resetFlowState() {
    setSendAmount("");
    setRateEstimate(undefined);
    setRecipient(undefined);
    setQuote(undefined);
    setPayoutMethod("mobile_money");
    setReasonForSending("");
    setProviderName("");
    setError("");
    setRateError("");
    setFlowKey((value) => value + 1);
    setActiveStep("market");
    setRecipientEntryMode("saved");
  }

  function clearTransactionDetails() {
    setQuote(undefined);
    window.sessionStorage.removeItem("createdQuote");
  }

  function clearSelectedRecipientDetails() {
    setRecipient(undefined);
    setReasonForSending("");
    setProviderName("");
    window.sessionStorage.removeItem("createdRecipient");
    window.sessionStorage.removeItem("reasonForSending");
    window.sessionStorage.removeItem("providerName");
  }

  function handleSendAmountChange(value: string) {
    setSendAmount(value);
    window.sessionStorage.setItem("sendAmount", value);
    clearTransactionDetails();
  }

  function handleMarketContinue() {
    if (!canContinueToRecipient) {
      return;
    }

    setActiveStep("recipient");
    setRecipientEntryMode(savedRecipientOptionAvailable ? "saved" : "new");
  }

  async function loadSavedRecipients(token = authSession?.token) {
    if (!token) {
      return;
    }

    setLoadingRecipients(true);
    setError("");

    try {
      const recipients = await getRecipients(token);
      setSavedRecipients(recipients);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoadingRecipients(false);
    }
  }

  async function prepareRecipientReview(
    nextRecipient: Recipient,
    method: PayoutMethod,
    nextReasonForSending: string,
    nextProviderName: string,
  ) {
    if (!authSession?.token) {
      throw new Error("Log in with a customer account first.");
    }

    if (!rateEstimate) {
      throw new Error("Choose countries and enter the amount to send first.");
    }

    if (!sendAmount || Number(sendAmount) <= 0) {
      throw new Error("Enter the amount to send first.");
    }

    setRecipient(nextRecipient);
    setPayoutMethod(method);
    setReasonForSending(nextReasonForSending);
    setProviderName(nextProviderName || "Bank deposit");
    clearTransactionDetails();

    window.sessionStorage.setItem("createdRecipient", JSON.stringify(nextRecipient));
    window.sessionStorage.setItem("payoutMethod", method);
    window.sessionStorage.setItem("reasonForSending", nextReasonForSending);
    window.sessionStorage.setItem(
      "providerName",
      nextProviderName || "Bank deposit",
    );

    const createdQuote = await createQuote(
      {
        corridor_id: rateEstimate.corridor_id,
        recipient_id: nextRecipient.id,
        payout_method: method,
        send_amount: sendAmount,
      },
      authSession.token,
    );

    handleQuoteCreated(createdQuote);
  }

  async function handleRecipientCreated(
    createdRecipient: Recipient,
    method: PayoutMethod,
    nextReasonForSending: string,
    nextProviderName: string,
  ) {
    await prepareRecipientReview(
      createdRecipient,
      method,
      nextReasonForSending,
      method === "mobile_money" ? nextProviderName : "Bank deposit",
    );

    if (authSession?.token) {
      loadSavedRecipients(authSession.token);
    }
  }

  function handleQuoteCreated(createdQuote: Quote) {
    setQuote(createdQuote);
    window.sessionStorage.setItem("createdQuote", JSON.stringify(createdQuote));
    setActiveStep("review");
  }

  return (
    <div className="premium-home">
      <AppNavbar />

      <main className="premium-send-main">
        <section className="send-intro">
          <div>
            <div className="premium-pill">Transfer details</div>
            <h1>Complete your money transfer</h1>
            <p className="lede">
              Enter the transfer amount, add the recipient, review the transaction,
              and continue to funding.
            </p>
          </div>
        </section>

        <section className="premium-send-layout" id="transfer-form">
          <div className="transfer-card">
            <div className="transfer-card-header">
              <div>
                <p>Secure transfer form</p>
                <h2>Send money</h2>
              </div>
              <span>Live flow</span>
            </div>

            <div className="transfer-flow">
              {loadingDiscovery ? (
                <p className="notice small">Loading country options...</p>
              ) : null}
              {loadingRate ? <p className="notice small">Refreshing rate...</p> : null}
              {error ? <pre className="error small">{error}</pre> : null}
              {rateError ? <pre className="error small">{rateError}</pre> : null}

              {activeStep === "market" ? (
                <>
                  <MarketSelector
                    key={`market-${flowKey}`}
                    senderCountries={senderCountries}
                    destinationCountries={destinationCountries}
                    rateEstimate={rateEstimate}
                    sourceCountryId={sourceCountryId}
                    destinationCountryId={destinationCountryId}
                    sendAmount={sendAmount}
                    exchangeRate={exchangeRate}
                    estimatedReceiveAmount={estimatedReceiveAmount}
                    sourceCurrencyCode={sourceCurrencyCode}
                    destinationCurrencyCode={destinationCurrencyCode}
                    onSourceCountryChange={(value) => {
                      setSourceCountryId(value);
                      window.sessionStorage.setItem("sourceCountryId", value);
                      clearTransactionDetails();
                    }}
                    onDestinationCountryChange={(value) => {
                      setDestinationCountryId(value);
                      window.sessionStorage.setItem("destinationCountryId", value);
                      clearSelectedRecipientDetails();
                      clearTransactionDetails();
                      setRecipientEntryMode("saved");
                    }}
                    onSendAmountChange={handleSendAmountChange}
                  />

                  <div className="step-next-action">
                    <button
                      type="button"
                      onClick={handleMarketContinue}
                      disabled={!canContinueToRecipient}
                    >
                      {loadingRate ? "Checking rate..." : "Continue to recipient"}
                    </button>
                  </div>
                </>
              ) : (
                <section className="step-summary" aria-label="Amount and countries summary">
                  <div className="step-summary-content">
                    <span className="step-number">1</span>
                    <div>
                      <p>Amount and countries</p>
                      <h2>
                        {sendAmount || "0.00"}
                        {sourceCurrencyCode ? ` ${sourceCurrencyCode}` : ""} to{" "}
                        {destinationCountryName}
                      </h2>
                      <span>
                        {sourceCountryName}
                        {estimatedReceiveAmount && destinationCurrencyCode
                          ? ` - Recipient gets ${estimatedReceiveAmount} ${destinationCurrencyCode}`
                          : ""}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="step-summary-edit"
                    onClick={() => setActiveStep("market")}
                  >
                    Edit
                  </button>
                </section>
              )}

              {activeStep === "recipient" ? (
                <section className="panel stack">
                  <div className="row">
                    <span className="step-number">2</span>
                    <div>
                      <h2>Recipient details</h2>
                      <p className="muted small">
                        Choose a saved recipient or add someone new.
                      </p>
                    </div>
                  </div>

                  <div
                    className="recipient-mode-toggle"
                    role="tablist"
                    aria-label="Recipient options"
                  >
                    <button
                      type="button"
                      className={
                        visibleRecipientEntryMode === "saved"
                          ? "secondary-button active"
                          : "secondary-button"
                      }
                      disabled={!savedRecipientOptionAvailable}
                      aria-selected={visibleRecipientEntryMode === "saved"}
                      role="tab"
                      onClick={() => setRecipientEntryMode("saved")}
                    >
                      Use saved recipient
                    </button>
                    <button
                      type="button"
                      className={
                        visibleRecipientEntryMode === "new"
                          ? "secondary-button active"
                          : "secondary-button"
                      }
                      aria-selected={visibleRecipientEntryMode === "new"}
                      role="tab"
                      onClick={() => setRecipientEntryMode("new")}
                    >
                      Add new recipient
                    </button>
                  </div>

                  {visibleRecipientEntryMode === "saved" ? (
                    <SavedRecipientSelector
                      key={`saved-recipient-${flowKey}`}
                      authToken={authSession?.token}
                      destinationCountry={selectedDestinationCountry}
                      loadingRecipients={loadingRecipients}
                      recipients={savedRecipients}
                      onSelected={prepareRecipientReview}
                    />
                  ) : (
                    <RecipientForm
                      key={`recipient-${flowKey}`}
                      authToken={authSession?.token}
                      destinationCountry={selectedDestinationCountry}
                      showHeading={false}
                      onCreated={handleRecipientCreated}
                    />
                  )}
                </section>
              ) : activeStep === "review" && recipient ? (
                <section className="step-summary" aria-label="Recipient summary">
                  <div className="step-summary-content">
                    <span className="step-number">2</span>
                    <div>
                      <p>Recipient details</p>
                      <h2>{recipientName || "Saved recipient"}</h2>
                      <span>
                        {quote?.payout_method === "bank_deposit"
                          ? "Bank deposit"
                          : "Mobile money"}
                        {providerName ? ` - ${providerName}` : ""}
                        {reasonForSending ? ` - ${reasonForSending}` : ""}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="step-summary-edit"
                    onClick={() => setActiveStep("recipient")}
                  >
                    Edit
                  </button>
                </section>
              ) : null}

              {activeStep === "review" && isReadyForReview ? (
                <TransferConfirmation
                  key={`confirm-${flowKey}`}
                  authToken={authSession?.token}
                  recipient={recipient}
                  quote={quote}
                  reasonForSending={reasonForSending}
                  providerName={providerName}
                />
              ) : null}
            </div>
          </div>

          <div id="transfer-summary">
            <FlowSummary
              rateEstimate={rateEstimate}
              recipient={recipient}
              quote={quote}
              sendAmount={sendAmount}
              exchangeRate={exchangeRate}
              estimatedReceiveAmount={estimatedReceiveAmount}
              reasonForSending={reasonForSending}
              providerName={providerName}
            />
          </div>
        </section>
      </main>
    </div>
  );
}
