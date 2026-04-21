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
    const savedSendAmount = window.sessionStorage.getItem("sendAmount") ?? "";
    const savedSourceCountryId = window.sessionStorage.getItem("sourceCountryId");
    const savedDestinationCountryId =
      window.sessionStorage.getItem("destinationCountryId");
    const savedPayoutMethod = window.sessionStorage.getItem("payoutMethod");
    const savedReason = window.sessionStorage.getItem("reasonForSending") ?? "";
    const savedProvider = window.sessionStorage.getItem("providerName") ?? "";

    if (savedRecipient) {
      setRecipient(JSON.parse(savedRecipient) as Recipient);
    }

    if (savedQuote) {
      setQuote(JSON.parse(savedQuote) as Quote);
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
      } catch (apiError) {
        setRateEstimate(undefined);
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

  const exchangeRate = rateEstimate?.exchange_rate ?? "";
  const estimatedReceiveAmount = rateEstimate?.receive_amount ?? "";

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

              <MarketSelector
                key={`market-${flowKey}`}
                senderCountries={senderCountries}
                destinationCountries={destinationCountries}
                sourceCountryId={sourceCountryId}
                destinationCountryId={destinationCountryId}
                sendAmount={sendAmount}
                exchangeRate={exchangeRate}
                estimatedReceiveAmount={estimatedReceiveAmount}
                sourceCurrencyCode={rateEstimate?.source_currency.code}
                destinationCurrencyCode={rateEstimate?.destination_currency.code}
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
                }}
                onSendAmountChange={handleSendAmountChange}
              />

              <section className="panel stack">
                <div className="row">
                  <span className="step-number">2</span>
                  <div>
                    <h2>Recipient details</h2>
                    <p className="muted small">
                      Use a saved recipient or add someone new.
                    </p>
                  </div>
                </div>

                <SavedRecipientSelector
                  key={`saved-recipient-${flowKey}`}
                  authToken={authSession?.token}
                  destinationCountry={selectedDestinationCountry}
                  loadingRecipients={loadingRecipients}
                  recipients={savedRecipients}
                  onSelected={prepareRecipientReview}
                />

                <div className="recipient-divider">
                  <span>or add a new recipient</span>
                </div>

                <RecipientForm
                  key={`recipient-${flowKey}`}
                  authToken={authSession?.token}
                  destinationCountry={selectedDestinationCountry}
                  showHeading={false}
                  onCreated={handleRecipientCreated}
                />
              </section>

              <TransferConfirmation
                key={`confirm-${flowKey}`}
                authToken={authSession?.token}
                recipient={recipient}
                quote={quote}
                reasonForSending={reasonForSending}
                providerName={providerName}
              />
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
