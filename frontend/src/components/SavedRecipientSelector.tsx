"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { Country, Recipient } from "@/lib/api";
import { formatApiError } from "@/lib/api";
import {
  type PayoutMethod,
  REASON_OPTIONS,
} from "@/lib/transfer-options";

type SavedRecipientSelectorProps = {
  authToken?: string;
  destinationCountry?: Country;
  loadingRecipients: boolean;
  recipients: Recipient[];
  onSelected: (
    recipient: Recipient,
    payoutMethod: PayoutMethod,
    reasonForSending: string,
    providerName: string,
  ) => void | Promise<void>;
};

function getDefaultMobileAccount(recipient?: Recipient) {
  return (
    recipient?.mobile_money_accounts.find((account) => account.is_default) ??
    recipient?.mobile_money_accounts[0]
  );
}

function getDefaultBankAccount(recipient?: Recipient) {
  return (
    recipient?.bank_accounts.find((account) => account.is_default) ??
    recipient?.bank_accounts[0]
  );
}

function getProviderName(recipient: Recipient, payoutMethod: PayoutMethod) {
  if (payoutMethod === "mobile_money") {
    return getDefaultMobileAccount(recipient)?.provider_name ?? "Mobile money";
  }

  return getDefaultBankAccount(recipient)?.bank_name ?? "Bank deposit";
}

function getRecipientLabel(recipient: Recipient) {
  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

export function SavedRecipientSelector({
  authToken,
  destinationCountry,
  loadingRecipients,
  recipients,
  onSelected,
}: SavedRecipientSelectorProps) {
  const [selectedRecipientId, setSelectedRecipientId] = useState("");
  const [payoutMethod, setPayoutMethod] = useState<PayoutMethod>("mobile_money");
  const [reasonForSending, setReasonForSending] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const destinationRecipients = useMemo(() => {
    if (!destinationCountry) {
      return [];
    }

    return recipients.filter(
      (recipient) => recipient.country.id === destinationCountry.id,
    );
  }, [destinationCountry, recipients]);

  const selectedRecipient = destinationRecipients.find(
    (recipient) => recipient.id === selectedRecipientId,
  );
  const hasMobileMoney = Boolean(
    selectedRecipient?.mobile_money_accounts.length,
  );
  const hasBankAccount = Boolean(selectedRecipient?.bank_accounts.length);

  useEffect(() => {
    const firstRecipient = destinationRecipients[0];

    if (!firstRecipient) {
      setSelectedRecipientId("");
      return;
    }

    if (!destinationRecipients.some((recipient) => recipient.id === selectedRecipientId)) {
      setSelectedRecipientId(firstRecipient.id);
    }
  }, [destinationRecipients, selectedRecipientId]);

  useEffect(() => {
    if (!selectedRecipient) {
      return;
    }

    if (payoutMethod === "mobile_money" && !hasMobileMoney && hasBankAccount) {
      setPayoutMethod("bank_deposit");
    }

    if (payoutMethod === "bank_deposit" && !hasBankAccount && hasMobileMoney) {
      setPayoutMethod("mobile_money");
    }
  }, [hasBankAccount, hasMobileMoney, payoutMethod, selectedRecipient]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authToken) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!selectedRecipient) {
      setError("Choose a saved recipient first.");
      return;
    }

    if (payoutMethod === "mobile_money" && !hasMobileMoney) {
      setError("This recipient does not have a mobile money account.");
      return;
    }

    if (payoutMethod === "bank_deposit" && !hasBankAccount) {
      setError("This recipient does not have a bank account.");
      return;
    }

    if (!reasonForSending) {
      setError("Select the reason for sending.");
      return;
    }

    setLoading(true);

    try {
      await onSelected(
        selectedRecipient,
        payoutMethod,
        reasonForSending,
        getProviderName(selectedRecipient, payoutMethod),
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="saved-recipient-box stack">
      <div>
        <h3>Use a saved recipient</h3>
        <p className="muted small">
          Choose someone you have already added for this destination.
        </p>
      </div>

      {!destinationCountry ? (
        <p className="notice small">Choose a destination country first.</p>
      ) : null}

      {loadingRecipients ? (
        <p className="notice small">Loading saved recipients...</p>
      ) : null}

      {!loadingRecipients && destinationCountry && destinationRecipients.length === 0 ? (
        <p className="muted small">
          No saved recipients for {destinationCountry.name} yet.
        </p>
      ) : null}

      {destinationRecipients.length > 0 ? (
        <form className="stack" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              Saved recipient
              <select
                value={selectedRecipientId}
                onChange={(event) => setSelectedRecipientId(event.target.value)}
              >
                {destinationRecipients.map((recipient) => (
                  <option key={recipient.id} value={recipient.id}>
                    {getRecipientLabel(recipient)}
                    {recipient.phone_number ? ` - ${recipient.phone_number}` : ""}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Reason for sending
              <select
                value={reasonForSending}
                onChange={(event) => setReasonForSending(event.target.value)}
                required
              >
                <option value="" disabled>
                  Select reason
                </option>
                {REASON_OPTIONS.map((reason) => (
                  <option key={reason} value={reason}>
                    {reason}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Payout method
              <select
                value={payoutMethod}
                onChange={(event) => setPayoutMethod(event.target.value as PayoutMethod)}
              >
                <option value="mobile_money" disabled={!hasMobileMoney}>
                  Mobile money
                </option>
                <option value="bank_deposit" disabled={!hasBankAccount}>
                  Bank deposit
                </option>
              </select>
            </label>

            <div className="saved-recipient-detail">
              <span>Account</span>
              <strong>
                {selectedRecipient
                  ? getProviderName(selectedRecipient, payoutMethod)
                  : "Pending"}
              </strong>
            </div>
          </div>

          {error ? <pre className="error small">{error}</pre> : null}

          <button type="submit" disabled={loading || !authToken || !selectedRecipient}>
            {loading ? "Preparing review..." : "Continue to review"}
          </button>
        </form>
      ) : null}
    </section>
  );
}
