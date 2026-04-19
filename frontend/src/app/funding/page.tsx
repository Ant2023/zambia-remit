"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import type { AuthSession, MockPaymentMethod, Transfer } from "@/lib/api";
import { formatApiError, getTransfer, markTransferFunded } from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";

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

  const isFunded =
    transfer?.status === "funding_received" ||
    transfer?.funding_status === "received";

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

                <button type="submit" disabled={loading || !transfer}>
                  {loading ? "Marking funded..." : "Mark as funded"}
                </button>
              </form>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
