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

const paymentMethods: Array<{ value: MockPaymentMethod; label: string }> = [
  { value: "debit_card", label: "Debit card" },
  { value: "bank_transfer", label: "Bank transfer" },
];

function formatProviderName(value: string) {
  return value.replaceAll("_", " ");
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
  const [paymentMethod, setPaymentMethod] =
    useState<MockPaymentMethod>("debit_card");
  const [cardholderName, setCardholderName] = useState("");
  const [cardNumber, setCardNumber] = useState("4242 4242 4242 4242");
  const [expiryMonth, setExpiryMonth] = useState("12");
  const [expiryYear, setExpiryYear] = useState("2030");
  const [cvv, setCvv] = useState("123");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingPaymentInstruction, setLoadingPaymentInstruction] = useState(false);
  const [authorizingPayment, setAuthorizingPayment] = useState(false);
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
        if (parsedTransfer.latest_payment_instruction) {
          setPaymentMethod(parsedTransfer.latest_payment_instruction.payment_method);
        }
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
      if (data.latest_payment_instruction) {
        setPaymentMethod(data.latest_payment_instruction.payment_method);
      }
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

    if (!paymentInstruction) {
      setError("Prepare payment instructions before confirming funding.");
      return;
    }

    setLoading(true);

    try {
      const updatedTransfer = await markTransferFunded(
        transfer.id,
        {
          payment_method: paymentMethod,
          payment_instruction_id: paymentInstruction.id,
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

  async function handlePreparePaymentInstruction() {
    setError("");

    if (!transfer) {
      setError("Load the transfer before preparing payment instructions.");
      return;
    }

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!senderProfile?.is_complete) {
      setError("Add sender details before preparing payment instructions.");
      return;
    }

    setLoadingPaymentInstruction(true);

    try {
      const instruction = await createPaymentInstruction(
        transfer.id,
        { payment_method: paymentMethod },
        authSession.token,
      );
      setPaymentInstruction(instruction);
      setTransfer((currentTransfer) =>
        currentTransfer
          ? {
              ...currentTransfer,
              latest_payment_instruction: instruction,
            }
          : currentTransfer,
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoadingPaymentInstruction(false);
    }
  }

  async function handleAuthorizePayment() {
    setError("");

    if (!transfer) {
      setError("Load the transfer before authorizing payment.");
      return;
    }

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!paymentInstruction) {
      setError("Prepare payment instructions before authorizing payment.");
      return;
    }

    if (
      paymentInstruction.payment_method !== "debit_card" ||
      paymentMethod !== "debit_card"
    ) {
      setError("Only debit card instructions support authorization.");
      return;
    }

    setAuthorizingPayment(true);

    try {
      const authorizedInstruction = await authorizeCardPaymentInstruction(
        transfer.id,
        paymentInstruction.id,
        {
          cardholder_name: cardholderName.trim(),
          card_number: cardNumber,
          expiry_month: Number(expiryMonth),
          expiry_year: Number(expiryYear),
          cvv,
        },
        authSession.token,
      );
      setPaymentInstruction(authorizedInstruction);
      setTransfer((currentTransfer) =>
        currentTransfer
          ? {
              ...currentTransfer,
              latest_payment_instruction: authorizedInstruction,
            }
          : currentTransfer,
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setAuthorizingPayment(false);
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
  const isCardPayment =
    paymentMethod === "debit_card" ||
    paymentInstruction?.payment_method === "debit_card";
  const isCardAuthorized =
    paymentInstruction?.status === "authorized" ||
    paymentInstruction?.status === "paid";
  const canConfirmFunding = Boolean(
    transfer &&
      senderProfile?.is_complete &&
      paymentInstruction &&
      (paymentInstruction.payment_method !== "debit_card" || isCardAuthorized),
  );
  const selectedPaymentMethodLabel =
    paymentMethods.find((method) => method.value === paymentMethod)?.label ??
    "Payment";

  return (
    <>
      <AppNavbar />
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
              <h2>Payment instructions</h2>

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
                      onChange={(event) => {
                        const nextMethod = event.target.value as MockPaymentMethod;
                        setPaymentMethod(nextMethod);
                        if (paymentInstruction?.payment_method !== nextMethod) {
                          setPaymentInstruction(null);
                        }
                      }}
                    >
                      {paymentMethods.map((method) => (
                        <option key={method.value} value={method.value}>
                          {method.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {paymentInstruction ? (
                    <div className="payment-instruction-box stack">
                      <div>
                        <p className="kicker">
                          {paymentInstruction.status_display}
                        </p>
                        <h3>
                          {paymentInstruction.instructions.title ??
                            selectedPaymentMethodLabel}
                        </h3>
                        <p className="muted small">
                          {paymentInstruction.instructions.summary ??
                            "Use these details to fund the transfer."}
                        </p>
                      </div>

                      <dl className="summary-list">
                        <div>
                          <dt>Total to pay</dt>
                          <dd>
                            {paymentInstruction.amount}{" "}
                            {paymentInstruction.currency.code}
                          </dd>
                        </div>
                        <div>
                          <dt>Payment reference</dt>
                          <dd>{paymentInstruction.provider_reference}</dd>
                        </div>
                        <div>
                          <dt>Provider</dt>
                          <dd>{formatProviderName(paymentInstruction.provider_name)}</dd>
                        </div>
                        {paymentInstruction.instructions.processor_display_name ? (
                          <div>
                            <dt>Processor</dt>
                            <dd>
                              {paymentInstruction.instructions.processor_display_name}
                            </dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.session_reference ? (
                          <div>
                            <dt>Session</dt>
                            <dd>
                              {paymentInstruction.instructions.session_reference}
                            </dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.next_action ? (
                          <div>
                            <dt>Next action</dt>
                            <dd>
                              {paymentInstruction.instructions.next_action.replaceAll(
                                "_",
                                " ",
                              )}
                            </dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.test_card ? (
                          <div>
                            <dt>Test card</dt>
                            <dd>{paymentInstruction.instructions.test_card}</dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.bank_name ? (
                          <div>
                            <dt>Bank</dt>
                            <dd>{paymentInstruction.instructions.bank_name}</dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.account_number ? (
                          <div>
                            <dt>Account number</dt>
                            <dd>{paymentInstruction.instructions.account_number}</dd>
                          </div>
                        ) : null}
                        {paymentInstruction.instructions.routing_number ? (
                          <div>
                            <dt>Routing number</dt>
                            <dd>{paymentInstruction.instructions.routing_number}</dd>
                          </div>
                        ) : null}
                      </dl>

                      {paymentInstruction.instructions.steps?.length ? (
                        <ol className="instruction-list">
                          {paymentInstruction.instructions.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ol>
                      ) : null}

                      {paymentInstruction.instructions.test_cards?.length ? (
                        <div className="stack">
                          <h3>Test outcomes</h3>
                          <dl className="summary-list">
                            {paymentInstruction.instructions.test_cards.map((card) => (
                              <div key={card.number}>
                                <dt>{card.number}</dt>
                                <dd>
                                  {card.outcome.replaceAll("_", " ")}
                                  {card.description ? ` - ${card.description}` : ""}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      ) : null}

                      {paymentInstruction.instructions.authorization_masked_card ? (
                        <dl className="summary-list">
                          <div>
                            <dt>Authorized card</dt>
                            <dd>
                              {paymentInstruction.instructions.authorization_masked_card}
                            </dd>
                          </div>
                          {paymentInstruction.instructions.authorization_reference ? (
                            <div>
                              <dt>Authorization</dt>
                              <dd>
                                {
                                  paymentInstruction.instructions
                                    .authorization_reference
                                }
                              </dd>
                            </div>
                          ) : null}
                        </dl>
                      ) : null}

                      {paymentInstruction.status === "pending_authorization" ? (
                        <p className="notice small">
                          Authorize the card before confirming that funding was
                          received.
                        </p>
                      ) : null}

                      {paymentInstruction.status === "requires_review" ? (
                        <p className="notice small">
                          This payment needs review before the transfer can move
                          forward.
                        </p>
                      ) : null}

                      {paymentInstruction.status === "failed" ? (
                        <p className="error small">
                          {paymentInstruction.status_reason ||
                            "The card authorization failed. Try a different test card or prepare a new instruction."}
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <p className="notice small">
                      Prepare payment instructions for {selectedPaymentMethodLabel}.
                    </p>
                  )}

                  <button
                    type="button"
                    className="secondary-button"
                    disabled={
                      loadingPaymentInstruction ||
                      !transfer ||
                      !senderProfile?.is_complete ||
                      !authSession
                    }
                    onClick={handlePreparePaymentInstruction}
                  >
                    {loadingPaymentInstruction
                      ? "Preparing..."
                      : paymentInstruction
                        ? "Prepare new instructions"
                        : "Prepare payment instructions"}
                  </button>

                  {paymentInstruction &&
                  paymentInstruction.payment_method === "debit_card" &&
                  !isFunded ? (
                    <div className="stack">
                      <div>
                        <p className="kicker">Card authorization</p>
                        <h3>Authorize your debit card</h3>
                        <p className="muted small">
                          Use one of the available test cards to simulate an
                          approved, declined, or review-required authorization.
                        </p>
                      </div>

                      <div className="stack">
                        <div className="form-grid">
                          <label>
                            Cardholder name
                            <input
                              value={cardholderName}
                              onChange={(event) =>
                                setCardholderName(event.target.value)
                              }
                              autoComplete="cc-name"
                              placeholder="Sam Sender"
                              required
                            />
                          </label>

                          <label>
                            Card number
                            <input
                              value={cardNumber}
                              onChange={(event) =>
                                setCardNumber(event.target.value)
                              }
                              autoComplete="cc-number"
                              inputMode="numeric"
                              placeholder="4242 4242 4242 4242"
                              required
                            />
                          </label>

                          <label>
                            Expiry month
                            <input
                              value={expiryMonth}
                              onChange={(event) =>
                                setExpiryMonth(event.target.value)
                              }
                              autoComplete="cc-exp-month"
                              inputMode="numeric"
                              placeholder="12"
                              required
                            />
                          </label>

                          <label>
                            Expiry year
                            <input
                              value={expiryYear}
                              onChange={(event) =>
                                setExpiryYear(event.target.value)
                              }
                              autoComplete="cc-exp-year"
                              inputMode="numeric"
                              placeholder="2030"
                              required
                            />
                          </label>

                          <label>
                            Security code
                            <input
                              value={cvv}
                              onChange={(event) => setCvv(event.target.value)}
                              autoComplete="cc-csc"
                              inputMode="numeric"
                              placeholder="123"
                              required
                            />
                          </label>
                        </div>

                        <button
                          type="button"
                          className="secondary-button"
                          disabled={
                            authorizingPayment ||
                            !cardholderName.trim() ||
                            !cardNumber.trim() ||
                            !expiryMonth.trim() ||
                            !expiryYear.trim() ||
                            !cvv.trim()
                          }
                          onClick={() => void handleAuthorizePayment()}
                        >
                          {authorizingPayment ? "Authorizing..." : "Authorize card"}
                        </button>
                      </div>
                    </div>
                  ) : null}

                  <label>
                    Funding note
                    <textarea
                      rows={3}
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      placeholder="Optional note for this funding event"
                    />
                  </label>

                  <button type="submit" disabled={loading || !canConfirmFunding}>
                    {loading
                      ? "Confirming..."
                      : isCardPayment && !isCardAuthorized
                        ? "Authorize card to continue"
                        : "Confirm funding received"}
                  </button>
                </form>
              )}
            </section>
          </div>
        </div>
      </div>
      </main>
    </>
  );
}
