"use client";

import { FormEvent, useState } from "react";
import type { Country, Recipient, RecipientPayload } from "@/lib/api";
import { createRecipient, formatApiError } from "@/lib/api";

type PayoutMethod = "mobile_money" | "bank_deposit";

const REASON_OPTIONS = [
  "Family support",
  "Education",
  "Medical expenses",
  "Rent or housing",
  "Bills and utilities",
  "Gift",
  "Business support",
  "Savings",
];

type RecipientFormProps = {
  authToken?: string;
  destinationCountry?: Country;
  onCreated: (
    recipient: Recipient,
    payoutMethod: PayoutMethod,
    reasonForSending: string,
    providerName: string,
  ) => void | Promise<void>;
};

export function RecipientForm({
  authToken,
  destinationCountry,
  onCreated,
}: RecipientFormProps) {
  const [payoutMethod, setPayoutMethod] = useState<PayoutMethod>("mobile_money");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authToken) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!destinationCountry) {
      setError("Choose a destination country first.");
      return;
    }

    const form = new FormData(event.currentTarget);
    const reasonForSending = String(form.get("reason_for_sending") ?? "");
    const providerName = String(form.get("provider_name") ?? "");

    const payload: RecipientPayload = {
      first_name: String(form.get("first_name") ?? ""),
      last_name: String(form.get("last_name") ?? ""),
      phone_number: String(form.get("phone_number") ?? ""),
      country_id: destinationCountry.id,
      relationship_to_sender: "",
      payout_method: payoutMethod,
    };

    if (payoutMethod === "mobile_money") {
      payload.mobile_money_account = {
        provider_name: providerName,
        mobile_number: String(form.get("mobile_number") ?? ""),
        account_name: String(form.get("mobile_account_name") ?? ""),
      };
    }

    if (payoutMethod === "bank_deposit") {
      payload.bank_account = {
        bank_name: String(form.get("bank_name") ?? ""),
        account_number: String(form.get("account_number") ?? ""),
        account_name: String(form.get("bank_account_name") ?? ""),
        branch_name: String(form.get("branch_name") ?? ""),
        swift_code: String(form.get("swift_code") ?? ""),
      };
    }

    setLoading(true);

    try {
      const recipient = await createRecipient(payload, authToken);
      await onCreated(recipient, payoutMethod, reasonForSending, providerName);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel stack">
      <div className="row">
        <span className="step-number">2</span>
        <div>
          <h2>Recipient details</h2>
          <p className="muted small">Enter who will receive the money.</p>
        </div>
      </div>

      <form className="stack" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            First name
            <input name="first_name" required />
          </label>

          <label>
            Last name
            <input name="last_name" required />
          </label>

          <label>
            Phone number
            <input name="phone_number" placeholder="+260971234567" required />
          </label>

          <label>
            Reason for sending
            <select name="reason_for_sending" required defaultValue="">
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
              <option value="mobile_money">Mobile money</option>
              <option value="bank_deposit">Bank deposit</option>
            </select>
          </label>

          {payoutMethod === "mobile_money" ? (
            <label>
              Provider
              <select name="provider_name" required>
                <option value="MTN">MTN</option>
                <option value="Airtel">Airtel</option>
              </select>
            </label>
          ) : null}
        </div>

        {payoutMethod === "mobile_money" ? (
          <div className="form-grid">
            <label>
              Mobile money number
              <input name="mobile_number" placeholder="+260971234567" required />
            </label>

            <label>
              Account name
              <input name="mobile_account_name" placeholder="Mary Banda" />
            </label>
          </div>
        ) : (
          <div className="form-grid">
            <label>
              Bank name
              <input name="bank_name" required />
            </label>

            <label>
              Account number
              <input name="account_number" required />
            </label>

            <label>
              Account name
              <input name="bank_account_name" />
            </label>

            <label>
              Branch
              <input name="branch_name" />
            </label>

            <label className="full">
              SWIFT code
              <input name="swift_code" />
            </label>
          </div>
        )}

        {error ? <pre className="error small">{error}</pre> : null}

        <button type="submit" disabled={loading || !destinationCountry || !authToken}>
          {loading ? "Preparing review..." : "Continue to review"}
        </button>
      </form>
    </section>
  );
}
