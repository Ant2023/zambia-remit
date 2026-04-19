"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FlowSummary } from "@/components/FlowSummary";
import { MarketSelector } from "@/components/MarketSelector";
import { RecipientForm } from "@/components/RecipientForm";
import { TransactionDetailsStep } from "@/components/TransactionDetailsStep";
import { TransferConfirmation } from "@/components/TransferConfirmation";
import {
  type AuthSession,
  type Country,
  type Quote,
  type RateEstimate,
  type Recipient,
  formatApiError,
  getDestinationCountries,
  getRateEstimate,
  getSenderCountries,
  logoutCustomer,
} from "@/lib/api";
import { clearAuthSession, getStoredAuthSession } from "@/lib/auth";

export default function Home() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [senderCountries, setSenderCountries] = useState<Country[]>([]);
  const [destinationCountries, setDestinationCountries] = useState<Country[]>([]);
  const [sourceCountryId, setSourceCountryId] = useState("");
  const [destinationCountryId, setDestinationCountryId] = useState("");
  const [sendAmount, setSendAmount] = useState("");
  const [rateEstimate, setRateEstimate] = useState<RateEstimate>();
  const [recipient, setRecipient] = useState<Recipient>();
  const [quote, setQuote] = useState<Quote>();
  const [payoutMethod, setPayoutMethod] = useState<"mobile_money" | "bank_deposit">(
    "mobile_money",
  );
  const [reasonForSending, setReasonForSending] = useState("");
  const [providerName, setProviderName] = useState("");
  const [loadingDiscovery, setLoadingDiscovery] = useState(true);
  const [loadingRate, setLoadingRate] = useState(false);
  const [error, setError] = useState("");
  const [rateError, setRateError] = useState("");

  useEffect(() => {
    setAuthSession(getStoredAuthSession());

    const savedRecipient = window.sessionStorage.getItem("createdRecipient");
    const savedQuote = window.sessionStorage.getItem("createdQuote");
    const savedSendAmount = window.sessionStorage.getItem("sendAmount") ?? "";
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
    setReasonForSending(savedReason);
    setProviderName(savedProvider);
  }, []);

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

        if (senders[0]) {
          setSourceCountryId(senders[0].id);
        }

        if (destinations[0]) {
          setDestinationCountryId(destinations[0].id);
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

  function clearTransactionDetails() {
    setQuote(undefined);
    window.sessionStorage.removeItem("createdQuote");
  }

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
    setRecipient(undefined);
    setQuote(undefined);
  }

  function handleSendAmountChange(value: string) {
    setSendAmount(value);
    window.sessionStorage.setItem("sendAmount", value);
    clearTransactionDetails();
  }

  function handleRecipientCreated(
    createdRecipient: Recipient,
    method: "mobile_money" | "bank_deposit",
    nextReasonForSending: string,
    nextProviderName: string,
  ) {
    setRecipient(createdRecipient);
    setPayoutMethod(method);
    setReasonForSending(nextReasonForSending);
    setProviderName(method === "mobile_money" ? nextProviderName : "Bank deposit");
    clearTransactionDetails();

    window.sessionStorage.setItem("createdRecipient", JSON.stringify(createdRecipient));
    window.sessionStorage.setItem("payoutMethod", method);
    window.sessionStorage.setItem("reasonForSending", nextReasonForSending);
    window.sessionStorage.setItem(
      "providerName",
      method === "mobile_money" ? nextProviderName : "Bank deposit",
    );
  }

  function handleQuoteCreated(createdQuote: Quote) {
    setQuote(createdQuote);
    window.sessionStorage.setItem("createdQuote", JSON.stringify(createdQuote));
  }

  return (
    <main className="page">
      <div className="shell stack">
        <header className="topbar">
          <div>
            <p className="kicker">Zambia Remit</p>
            <h1>Send money to Zambia</h1>
            <p className="lede">
              Create a recipient, review the transaction details, and track the
              transfer from funding through payout.
            </p>
            <Link className="text-link" href="/history">
              View transaction history
            </Link>
          </div>

          <section className="panel stack">
            <h2>Customer account</h2>
            {authSession ? (
              <>
                <p className="muted small">Signed in as {authSession.user.email}</p>
                <button type="button" onClick={handleLogout}>
                  Log out
                </button>
              </>
            ) : (
              <>
                <p className="muted small">
                  Log in or create a customer account before adding a recipient.
                </p>
                <Link href="/login">
                  <button type="button">Log in</button>
                </Link>
              </>
            )}
          </section>
        </header>

        {loadingDiscovery ? <p className="notice">Loading country options...</p> : null}
        {loadingRate ? <p className="notice">Refreshing rate...</p> : null}
        {error ? <pre className="error small">{error}</pre> : null}
        {rateError ? <pre className="error small">{rateError}</pre> : null}

        <div className="grid">
          <div className="stack">
            <MarketSelector
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
                clearTransactionDetails();
              }}
              onDestinationCountryChange={(value) => {
                setDestinationCountryId(value);
                setRecipient(undefined);
                setReasonForSending("");
                setProviderName("");
                window.sessionStorage.removeItem("createdRecipient");
                window.sessionStorage.removeItem("reasonForSending");
                window.sessionStorage.removeItem("providerName");
                clearTransactionDetails();
              }}
              onSendAmountChange={handleSendAmountChange}
            />

            <RecipientForm
              authToken={authSession?.token}
              destinationCountry={selectedDestinationCountry}
              onCreated={handleRecipientCreated}
            />

            <TransactionDetailsStep
              authToken={authSession?.token}
              rateEstimate={rateEstimate}
              recipient={recipient}
              payoutMethod={payoutMethod}
              sendAmount={sendAmount}
              exchangeRate={exchangeRate}
              estimatedReceiveAmount={estimatedReceiveAmount}
              reasonForSending={reasonForSending}
              providerName={providerName}
              quote={quote}
              onCreated={handleQuoteCreated}
            />

            <TransferConfirmation
              authToken={authSession?.token}
              recipient={recipient}
              quote={quote}
              reasonForSending={reasonForSending}
            />
          </div>

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
      </div>
    </main>
  );
}
