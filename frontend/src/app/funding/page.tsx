"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";
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
  confirmStripePaymentInstruction,
  createPaymentInstruction,
  formatApiError,
  getSenderCountries,
  getSenderProfile,
  getTransfer,
  markTransferFunded,
  updateSenderProfile,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";
import { getFxRateSourceSummary } from "@/lib/fx";

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "",
);

type SelectedPaymentMethod = MockPaymentMethod | "";

const cardPaymentMethods = new Set<MockPaymentMethod>([
  "credit_card",
  "debit_card",
]);

function isCardPaymentMethod(value?: SelectedPaymentMethod | null) {
  return value ? cardPaymentMethods.has(value) : false;
}

function getUserDisplayName(user?: AuthSession["user"]) {
  if (!user) return "";
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

type StripeCardFormProps = {
  clientSecret: string;
  paymentIntentId: string;
  instruction: PaymentInstruction;
  transfer: Transfer;
  authToken: string;
  onSuccess: (updatedTransfer: Transfer) => void;
  onError: (message: string) => void;
  loading: boolean;
  setLoading: (loading: boolean) => void;
};

function StripeCardForm({
  clientSecret,
  paymentIntentId,
  instruction,
  transfer,
  authToken,
  onSuccess,
  onError,
  loading,
  setLoading,
}: StripeCardFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const [ready, setReady] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!stripe || !elements) return;

    setLoading(true);
    onError("");

    const { error: submitError } = await elements.submit();
    if (submitError) {
      onError(submitError.message ?? "Failed to prepare payment. Please try again.");
      setLoading(false);
      return;
    }

    const { error: confirmError } = await stripe.confirmPayment({
      elements,
      redirect: "if_required",
      confirmParams: {
        return_url: window.location.href,
      },
    });

    if (confirmError) {
      onError(confirmError.message ?? "Payment failed. Please try again.");
      setLoading(false);
      return;
    }

    try {
      const confirmedInstruction = await confirmStripePaymentInstruction(
        transfer.id,
        instruction.id,
        { payment_intent_id: paymentIntentId },
        authToken,
      );

      if (
        confirmedInstruction.status !== "authorized" &&
        confirmedInstruction.status !== "paid"
      ) {
        onError(
          confirmedInstruction.status_reason ||
            "Payment verification failed. Please contact support.",
        );
        setLoading(false);
        return;
      }

      const updatedTransfer = await markTransferFunded(
        transfer.id,
        {
          payment_method: instruction.payment_method,
          payment_instruction_id: instruction.id,
          note: "",
        },
        authToken,
      );

      onSuccess(updatedTransfer);
    } catch (apiError) {
      onError(formatApiError(apiError));
      setLoading(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <PaymentElement onReady={() => setReady(true)} />
      <button
        type="submit"
        className={ready ? "payment-submit-button is-ready" : "payment-submit-button"}
        disabled={loading || !stripe || !elements || !ready}
      >
        {loading ? "Processing..." : "Pay with card"}
      </button>
    </form>
  );
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
  const creatingInstructionRef = useRef(false);

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
        ? { ...currentTransfer, latest_payment_instruction: instruction }
        : currentTransfer,
    );
  }

  function syncTransfer(updatedTransfer: Transfer) {
    setTransfer(updatedTransfer);
    window.sessionStorage.setItem("latestTransfer", JSON.stringify(updatedTransfer));
  }

  async function createInstructionForMethod(method: MockPaymentMethod) {
    if (!transfer || !authSession?.token || !senderProfile?.is_complete) return;
    if (creatingInstructionRef.current) return;
    creatingInstructionRef.current = true;
    setLoading(true);
    setError("");
    try {
      const instruction = await createPaymentInstruction(
        transfer.id,
        { payment_method: method },
        authSession.token,
      );
      syncPaymentInstruction(instruction);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
      creatingInstructionRef.current = false;
    }
  }

  function handlePaymentMethodChange(method: SelectedPaymentMethod) {
    setPaymentMethod(method);
    if (paymentInstruction?.payment_method !== method) {
      setPaymentInstruction(null);
    }
    if (
      method &&
      isCardPaymentMethod(method) &&
      transfer &&
      authSession?.token &&
      senderProfile?.is_complete
    ) {
      createInstructionForMethod(method);
    }
  }

  async function handleBankTransferSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (!transfer || !authSession?.token) throw new Error("Missing transfer or session.");

      let instruction = paymentInstruction;
      if (!instruction || instruction.payment_method !== paymentMethod) {
        instruction = await createPaymentInstruction(
          transfer.id,
          { payment_method: paymentMethod as MockPaymentMethod },
          authSession.token,
        );
        syncPaymentInstruction(instruction);
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

  const isStripeInstruction =
    paymentInstruction?.instructions?.integration_mode === "stripe_payment_element";
  const stripeClientSecret = isStripeInstruction
    ? (paymentInstruction?.instructions?.client_secret ?? "")
    : "";
  const stripePaymentIntentId = isStripeInstruction
    ? (paymentInstruction?.instructions?.payment_intent_id ?? "")
    : "";

  const showStripeForm =
    isCardPaymentMethod(paymentMethod) &&
    isStripeInstruction &&
    stripeClientSecret &&
    transfer &&
    authSession?.token &&
    senderProfile?.is_complete &&
    !isFunded;

  const showBankTransferForm =
    paymentMethod === "bank_transfer" && !isFunded;

  const canSubmitBankTransfer = Boolean(
    transfer && senderProfile?.is_complete && authSession?.token && !isFunded,
  );

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
                  <div className="stack">
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
                          handlePaymentMethodChange(
                            event.target.value as SelectedPaymentMethod,
                          );
                        }}
                      >
                        <option value="" disabled>
                          Choose payment method
                        </option>
                        <option value="credit_card">Credit card</option>
                        <option value="debit_card">Debit card</option>
                        <option value="bank_transfer">Bank transfer</option>
                      </select>
                    </label>

                    {isCardPaymentMethod(paymentMethod) && loading && !showStripeForm ? (
                      <p className="muted small">Preparing secure payment form...</p>
                    ) : null}

                    {showStripeForm ? (
                      <Elements
                        stripe={stripePromise}
                        options={{
                          clientSecret: stripeClientSecret,
                          appearance: {
                            theme: "stripe",
                            variables: {
                              colorPrimary: "#10b981",
                              borderRadius: "8px",
                            },
                          },
                        }}
                      >
                        <StripeCardForm
                          clientSecret={stripeClientSecret}
                          paymentIntentId={stripePaymentIntentId}
                          instruction={paymentInstruction!}
                          transfer={transfer!}
                          authToken={authSession!.token}
                          loading={loading}
                          setLoading={setLoading}
                          onError={(msg) => setError(msg)}
                          onSuccess={(updatedTransfer) => {
                            syncTransfer(updatedTransfer);
                            router.push(
                              `/success?transferId=${updatedTransfer.id}&funded=1`,
                            );
                          }}
                        />
                      </Elements>
                    ) : null}

                    {showBankTransferForm ? (
                      <form className="stack" onSubmit={handleBankTransferSubmit}>
                        <button
                          type="submit"
                          className={
                            canSubmitBankTransfer
                              ? "payment-submit-button is-ready"
                              : "payment-submit-button"
                          }
                          disabled={loading || !canSubmitBankTransfer}
                        >
                          {loading ? "Processing..." : "Pay with bank transfer"}
                        </button>
                      </form>
                    ) : null}
                  </div>
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
                    <dt>Exchange rate</dt>
                    <dd>
                      1 {transfer.source_currency_details.code} ={" "}
                      {transfer.exchange_rate}{" "}
                      {transfer.destination_currency_details.code}
                    </dd>
                  </div>
                  <div>
                    <dt>FX source</dt>
                    <dd>{getFxRateSourceSummary(transfer)}</dd>
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
