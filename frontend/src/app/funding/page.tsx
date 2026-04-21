"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type {
  AuthSession,
  Country,
  MockPaymentMethod,
  PaymentInstruction,
  SenderProfile,
  SenderProfilePayload,
  Transfer,
} from "@/lib/api";
import {
  authorizeCardPaymentInstruction,
  createPaymentInstruction,
  formatApiError,
  getSenderCountries,
  getSenderProfile,
  getTransfer,
  markTransferFunded,
  updateSenderProfile,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";

type SelectedPaymentMethod = MockPaymentMethod | "";

const paymentMethods: Array<{
  value: MockPaymentMethod;
  label: string;
}> = [
  { value: "credit_card", label: "Credit card" },
  { value: "debit_card", label: "Debit card" },
  { value: "bank_transfer", label: "Bank transfer" },
];

const cardPaymentMethods = new Set<MockPaymentMethod>([
  "credit_card",
  "debit_card",
]);

const sandboxCardAuthorization = {
  card_number: "4242 4242 4242 4242",
  expiry_month: 12,
  expiry_year: 2030,
  cvv: "123",
};

function isCardPaymentMethod(value?: SelectedPaymentMethod | null) {
  return value ? cardPaymentMethods.has(value) : false;
}

function getUserDisplayName(user?: AuthSession["user"]) {
  if (!user) {
    return "";
  }

  return [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
}

function getSenderDisplayName(
  authSession: AuthSession | null,
  senderProfile: SenderProfile | null,
) {
  return (
    [senderProfile?.first_name, senderProfile?.last_name]
      .filter(Boolean)
      .join(" ")
      .trim() ||
    getUserDisplayName(authSession?.user) ||
    "MbongoPay customer"
  );
}

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
  const [paymentInstruction, setPaymentInstruction] =
    useState<PaymentInstruction | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<SelectedPaymentMethod>("");
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
        setPaymentInstruction(parsedTransfer.latest_payment_instruction);
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
      setPaymentInstruction(data.latest_payment_instruction);
      window.sessionStorage.setItem("latestTransfer", JSON.stringify(data));
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  function syncPaymentInstruction(instruction: PaymentInstruction) {
    setPaymentInstruction(instruction);
    setTransfer((currentTransfer) =>
      currentTransfer
        ? {
            ...currentTransfer,
            latest_payment_instruction: instruction,
          }
        : currentTransfer,
    );
  }

  function syncTransfer(updatedTransfer: Transfer) {
    setTransfer(updatedTransfer);
    window.sessionStorage.setItem(
      "latestTransfer",
      JSON.stringify(updatedTransfer),
    );
  }

  async function ensurePaymentInstruction() {
    const selectedMethod = paymentMethod;

    if (!transfer) {
      throw new Error("Load the transfer before choosing payment.");
    }

    if (!authSession?.token) {
      throw new Error("Log in with a customer account first.");
    }

    if (!senderProfile?.is_complete) {
      throw new Error("Add sender details before paying for this transaction.");
    }

    if (!selectedMethod) {
      throw new Error("Choose a payment method first.");
    }

    if (paymentInstruction?.payment_method === selectedMethod) {
      return paymentInstruction;
    }

    const instruction = await createPaymentInstruction(
      transfer.id,
      { payment_method: selectedMethod },
      authSession.token,
    );
    syncPaymentInstruction(instruction);
    return instruction;
  }

  async function completePayment(instruction: PaymentInstruction) {
    if (!transfer) {
      throw new Error("Load the transfer before completing payment.");
    }

    if (!authSession?.token) {
      throw new Error("Log in with a customer account first.");
    }

    const updatedTransfer = await markTransferFunded(
      transfer.id,
      {
        payment_method: instruction.payment_method,
        payment_instruction_id: instruction.id,
        note: "",
      },
      authSession.token,
    );
    syncTransfer(updatedTransfer);
    router.push(`/success?transferId=${updatedTransfer.id}&funded=1`);
  }

  async function handlePaymentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const instruction = await ensurePaymentInstruction();

      if (isCardPaymentMethod(instruction.payment_method)) {
        const authorizedInstruction = await authorizeCardPaymentInstruction(
          instruction.transfer,
          instruction.id,
          {
            cardholder_name: getSenderDisplayName(authSession, senderProfile),
            card_number: sandboxCardAuthorization.card_number,
            expiry_month: sandboxCardAuthorization.expiry_month,
            expiry_year: sandboxCardAuthorization.expiry_year,
            cvv: sandboxCardAuthorization.cvv,
            billing_postal_code: senderProfile?.postal_code?.trim() || "80202",
          },
          authSession?.token ?? "",
        );
        syncPaymentInstruction(authorizedInstruction);

        if (
          authorizedInstruction.status !== "authorized" &&
          authorizedInstruction.status !== "paid"
        ) {
          setError(
            authorizedInstruction.status_reason ||
              "The card authorization failed. Try a different payment method.",
          );
          return;
        }

        await completePayment(authorizedInstruction);
        return;
      }

      await completePayment(instruction);
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
  const senderFirstName =
    senderProfile?.first_name || authSession?.user.first_name || "";
  const senderLastName =
    senderProfile?.last_name || authSession?.user.last_name || "";
  const signedInLabel =
    getUserDisplayName(authSession?.user) || authSession?.user.email || "";
  const canSubmitPayment = Boolean(
    transfer &&
      senderProfile?.is_complete &&
      paymentMethod &&
      authSession?.token &&
      !isFunded,
  );
  const selectedPaymentMethodLabel =
    paymentMethods.find((method) => method.value === paymentMethod)?.label ??
    "payment method";
  const paymentButtonLabel = paymentMethod
    ? isCardPaymentMethod(paymentMethod)
      ? `Authorize ${selectedPaymentMethodLabel.toLowerCase()} and pay`
      : `Pay with ${selectedPaymentMethodLabel.toLowerCase()}`
    : "Choose payment method";

  return (
    <div className="premium-home">
      <AppNavbar />

      <main className="premium-send-main">
        <section className="send-intro">
          <div>
            <div className="premium-pill">Payment</div>
            <h1>Pay for your transaction</h1>
            <p className="lede">
              Confirm your sender details, choose one payment method, and finish
              the transfer.
            </p>
            <Link className="text-link" href="/history">
              View transaction history
            </Link>
          </div>
        </section>

        <section className="premium-send-layout">
          <div className="transfer-card">
            <div className="transfer-card-header">
              <div>
                <p>Secure payment step</p>
                <h2>Sender and payment</h2>
              </div>
              <span>{signedInLabel || "Customer"}</span>
            </div>

            <div className="transfer-flow">
              {error ? <pre className="error small">{error}</pre> : null}

              <section className="panel stack">
                <div>
                  <p className="kicker">Sender details</p>
                  <h2>Confirm your information</h2>
                  <p className="muted small">
                    Your signup name is filled in already. Add anything still
                    needed to complete the payment.
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
                          defaultValue={senderFirstName}
                          required
                        />
                      </label>

                      <label>
                        Last name
                        <input
                          name="last_name"
                          autoComplete="family-name"
                          defaultValue={senderLastName}
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

                <div className="section-divider" />

                <div>
                  <p className="kicker">Payment</p>
                  <h2>Choose how to pay</h2>
                  <p className="muted small">
                    Select a payment method to activate the final button.
                  </p>
                </div>

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
                  <form className="stack" onSubmit={handlePaymentSubmit}>
                    {!senderProfile?.is_complete ? (
                      <p className="notice small">
                        Save sender details before completing payment.
                      </p>
                    ) : null}

                    <label>
                      Payment method
                      <select
                        value={paymentMethod}
                        onChange={(event) => {
                          const nextMethod = event.target.value as SelectedPaymentMethod;
                          setPaymentMethod(nextMethod);
                          if (paymentInstruction?.payment_method !== nextMethod) {
                            setPaymentInstruction(null);
                          }
                        }}
                      >
                        <option value="" disabled>
                          Choose payment method
                        </option>
                        {paymentMethods.map((method) => (
                          <option key={method.value} value={method.value}>
                            {method.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <button
                      type="submit"
                      className={
                        canSubmitPayment
                          ? "payment-submit-button is-ready"
                          : "payment-submit-button"
                      }
                      disabled={loading || !canSubmitPayment}
                    >
                      {loading ? "Processing..." : paymentButtonLabel}
                    </button>
                  </form>
                )}
              </section>
            </div>
          </div>

          <div id="transfer-summary">
            <section className="panel stack">
              <p className="kicker">Transaction summary</p>
              <h2>Review</h2>

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
                <p className="muted small">Load the transaction to continue.</p>
              )}

              <button type="button" onClick={() => loadTransfer()}>
                {loading ? "Loading..." : "Refresh transaction"}
              </button>
            </section>
          </div>
        </section>
      </main>
    </div>
  );
}
