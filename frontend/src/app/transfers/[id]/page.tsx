"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { AuthSession, Transfer } from "@/lib/api";
import { formatApiError, getTransfer } from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";
import { getFxRateSourceSummary } from "@/lib/fx";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function TransferDetailPage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [transferId, setTransferId] = useState("");
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = window.location.pathname.split("/").filter(Boolean).at(-1) ?? "";
    const savedSession = getStoredAuthSession();

    setTransferId(id);
    setAuthSession(savedSession);

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

  const needsFunding =
    transfer?.status === "awaiting_funding" &&
    transfer.funding_status !== "received";

  return (
    <>
      <AppNavbar />
      <main className="page">
      <div className="shell stack">
        <header className="topbar">
          <div>
            <p className="kicker">Transaction</p>
            <h1>{transfer?.reference ?? "Transaction detail"}</h1>
            <p className="lede">
              View transaction status, funding progress, and status history.
            </p>
            <Link className="text-link" href="/history">
              Back to history
            </Link>
          </div>

          <section className="panel stack">
            <h2>Customer account</h2>
            {authSession ? (
              <>
                <p className="muted small">Signed in as {authSession.user.email}</p>
                <button type="button" onClick={() => loadTransfer()}>
                  {loading ? "Loading..." : "Load transaction"}
                </button>
              </>
            ) : (
              <>
                <p className="muted small">Log in to view this transaction.</p>
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
            <h2>Details</h2>

            {transfer ? (
              <>
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
                      1 {transfer.source_currency_details.code} = {transfer.exchange_rate}{" "}
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

                {needsFunding ? (
                  <Link href={`/funding?transferId=${transfer.id}`}>
                    <button type="button">Complete funding</button>
                  </Link>
                ) : null}
              </>
            ) : (
              <p className="muted">Load the transaction to view details.</p>
            )}
          </section>

          <section className="panel stack">
            <h2>Status history</h2>

            {transfer?.status_events.length ? (
              <ol className="event-list">
                {transfer.status_events.map((event) => (
                  <li key={event.id}>
                    <strong>{event.to_status_display}</strong>
                    <span>{formatDate(event.created_at)}</span>
                    {event.note ? <p>{event.note}</p> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">No status events found yet.</p>
            )}
          </section>
        </div>
      </div>
      </main>
    </>
  );
}
