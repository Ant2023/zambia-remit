"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import type {
  AuthSession,
  Country,
  MockPaymentMethod,
  SenderProfile,
  SenderProfilePayload,
  Transfer,
} from "@/lib/api";
import {
  formatApiError,
  getSenderCountries,
  getSenderProfile,
  getTransfer,
  markTransferFunded,
  updateSenderProfile,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";

const paymentMethods: Array<{ value: MockPaymentMethod; label: string }> = [
  { value: "debit_card", label: "Debit card" },
  { value: "bank_transfer", label: "Bank transfer" },
];

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function FundingPage() {
  const router = useRouter();
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [transferId, setTransferId] = useState("");
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [senderProfile, setSenderProfile] = useState<SenderProfile | null>(null);
  const [senderCountries, setSenderCountries] = useState<Country[]>([]);
  const [editingSenderDetails, setEditingSenderDetails] = useState(false);
  const [paymentMethod, setPaymentMethod] =
    useState<MockPaymentMethod>("debit_card");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("transferId") ?? "";
    const savedSession = getStoredAuthSession();
    const savedTransfer = window.sessionStorage.getItem("latestTransfer");

    setTransferId(id);
    setAuthSession(savedSession);

    if (savedSession) {
      loadSenderProfile(savedSession.token);
      loadSenderCountryOptions();
    }

    if (savedTransfer) {
      const parsedTransfer = JSON.parse(savedTransfer) as Transfer;
      if (!id || parsedTransfer.id === id) {
        setTransfer(parsedTransfer);
      }
    }

    if (id && savedSession) {
      loadTransfer(id, savedSession.token);
    }
  }, []);

  async function loadSenderCountryOptions() {
    try {
      const countries = await getSenderCountries();
      setSenderCountries(countries);
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  async function loadSenderProfile(token = authSession?.token) {
    setError("");

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    try {
      const profile = await getSenderProfile(token);
      setSenderProfile(profile);
      setEditingSenderDetails(!profile.is_complete);
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  async function loadTransfer(id = transferId, token = authSession?.token) {
    setError("");

    if (!id) {
      setError("Missing transfer id.");
      return;
    }

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    setLoading(true);

    try {
      const data = await getTransfer(id, token);
      setTransfer(data);
      window.sessionStorage.setItem("latestTransfer", JSON.stringify(data));
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!transfer) {
      setError("Load the transfer before marking it funded.");
      return;
    }

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!senderProfile?.is_complete) {
      setError("Add sender details before funding this transaction.");
      return;
    }

    setLoading(true);

    try {
      const updatedTransfer = await markTransferFunded(
        transfer.id,
        {
          payment_method: paymentMethod,
          note,
        },
        authSession.token,
      );
      setTransfer(updatedTransfer);
      window.sessionStorage.setItem(
        "latestTransfer",
        JSON.stringify(updatedTransfer),
      );
      router.push(`/success?transferId=${updatedTransfer.id}&funded=1`);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  async function handleSenderDetailsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    const form = new FormData(event.currentTarget);
    const payload: SenderProfilePayload = {
      first_name: String(form.get("first_name") ?? "").trim(),
      last_name: String(form.get("last_name") ?? "").trim(),
      phone_number: String(form.get("phone_number") ?? "").trim(),
      country_id: String(form.get("country_id") ?? ""),
    };

    if (!payload.first_name || !payload.last_name || !payload.phone_number) {
      setError("Enter your first name, last name, and phone number.");
      return;
    }

    if (!payload.country_id) {
      setError("Choose your country of residence.");
      return;
    }

    setLoading(true);

    try {
      const profile = await updateSenderProfile(payload, authSession.token);
      setSenderProfile(profile);
      setEditingSenderDetails(false);

      const updatedSession = {
        ...authSession,
        user: {
          ...authSession.user,
          first_name: profile.first_name,
          last_name: profile.last_name,
        },
      };
      setAuthSession(updatedSession);
      saveAuthSession(updatedSession);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  const isFunded =
    transfer?.status === "funding_received" ||
    transfer?.funding_status === "received";
  const canConfirmFunding = Boolean(transfer && senderProfile?.is_complete);

  return (
    <main className="page">
      <div className="shell stack">
        <header className="topbar">
          <div>
            <p className="kicker">Funding</p>
            <h1>Fund your transaction</h1>
            <p className="lede">
              Choose a payment method and confirm that funding has been received
              for this transaction.
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
                <button type="button" onClick={() => loadTransfer()}>
                  {loading ? "Loading..." : "Refresh transaction"}
                </button>
              </>
            ) : (
              <>
                <p className="muted small">Log in to fund this transaction.</p>
                <Link href="/login">
                  <button type="button">Log in</button>
                </Link>
              </>
            )}
          </section>
        </header>

        {error ? <pre className="error small">{error}</pre> : null}

        <div className="grid">
          <section className="panel stack">
            <h2>Transaction summary</h2>

            {transfer ? (
              <dl className="summary-list">
                <div>
                  <dt>Reference</dt>
                  <dd>{transfer.reference}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{transfer.status_display}</dd>
                </div>
                <div>
                  <dt>Funding</dt>
                  <dd>{transfer.funding_status_display}</dd>
                </div>
                <div>
                  <dt>Send amount</dt>
                  <dd>{transfer.send_amount}</dd>
                </div>
                <div>
                  <dt>Recipient receives</dt>
                  <dd>{transfer.receive_amount}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{formatDate(transfer.created_at)}</dd>
                </div>
              </dl>
            ) : (
              <p className="muted">Load the transaction to continue.</p>
            )}
          </section>

          <div className="stack">
            <section className="panel stack">
              <div>
                <p className="kicker">Sender details</p>
                <h2>Confirm your information</h2>
                <p className="muted small">
                  These details are saved to your customer profile for future
                  transfers.
                </p>
              </div>

              {senderProfile?.is_complete && !editingSenderDetails ? (
                <>
                  <dl className="summary-list">
                    <div>
                      <dt>Name</dt>
                      <dd>
                        {senderProfile.first_name} {senderProfile.last_name}
                      </dd>
                    </div>
                    <div>
                      <dt>Phone</dt>
                      <dd>{senderProfile.phone_number}</dd>
                    </div>
                    <div>
                      <dt>Residence</dt>
                      <dd>{senderProfile.country?.name ?? "Not provided"}</dd>
                    </div>
                  </dl>
                  {!isFunded ? (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setEditingSenderDetails(true)}
                    >
                      Change sender details
                    </button>
                  ) : null}
                </>
              ) : (
                <form
                  key={senderProfile?.updated_at ?? "sender-details"}
                  className="stack"
                  onSubmit={handleSenderDetailsSubmit}
                >
                  <div className="form-grid">
                    <label>
                      First name
                      <input
                        name="first_name"
                        autoComplete="given-name"
                        defaultValue={senderProfile?.first_name ?? ""}
                        required
                      />
                    </label>

                    <label>
                      Last name
                      <input
                        name="last_name"
                        autoComplete="family-name"
                        defaultValue={senderProfile?.last_name ?? ""}
                        required
                      />
                    </label>

                    <label>
                      Phone number
                      <input
                        name="phone_number"
                        autoComplete="tel"
                        placeholder="+12025550123"
                        defaultValue={senderProfile?.phone_number ?? ""}
                        required
                      />
                    </label>

                    <label>
                      Country of residence
                      <select
                        name="country_id"
                        defaultValue={senderProfile?.country?.id ?? ""}
                        required
                      >
                        <option value="" disabled>
                          Select country
                        </option>
                        {senderCountries.map((country) => (
                          <option key={country.id} value={country.id}>
                            {country.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="row">
                    <button type="submit" disabled={loading || !authSession}>
                      {loading ? "Saving..." : "Save sender details"}
                    </button>
                    {senderProfile?.is_complete ? (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => setEditingSenderDetails(false)}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </div>
                </form>
              )}
            </section>

            <section className="panel stack">
              <h2>Payment confirmation</h2>

              {isFunded ? (
                <>
                  <p className="success small">
                    Funding has been received for this transaction.
                  </p>
                  <Link href={`/success?transferId=${transfer?.id ?? transferId}`}>
                    <button type="button">Continue</button>
                  </Link>
                </>
              ) : (
                <form className="stack" onSubmit={handleSubmit}>
                  {!senderProfile?.is_complete ? (
                    <p className="notice small">
                      Add sender details above before confirming funding.
                    </p>
                  ) : null}

                  <label>
                    Payment method
                    <select
                      value={paymentMethod}
                      onChange={(event) =>
                        setPaymentMethod(event.target.value as MockPaymentMethod)
                      }
                    >
                      {paymentMethods.map((method) => (
                        <option key={method.value} value={method.value}>
                          {method.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Internal note
                    <textarea
                      rows={3}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      placeholder="Optional note for this funding event"
                    />
                  </label>

                  <button type="submit" disabled={loading || !canConfirmFunding}>
                    {loading ? "Marking funded..." : "Mark as funded"}
                  </button>
                </form>
              )}
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}
