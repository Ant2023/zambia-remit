"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { AuthSession, Transfer } from "@/lib/api";
import { formatApiError, getTransfers } from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function HistoryRow({ transfer }: { transfer: Transfer }) {
  const detailHref = `/transfers/${transfer.id}`;

  return (
    <tr>
      <td>
        <Link className="text-link" href={detailHref}>
          {transfer.reference}
        </Link>
      </td>
      <td>{transfer.status_display}</td>
      <td>{transfer.funding_status_display}</td>
      <td>{transfer.send_amount}</td>
      <td>{transfer.receive_amount}</td>
      <td>{formatDate(transfer.created_at)}</td>
      <td>
        {transfer.status === "awaiting_funding" ? (
          <Link className="text-link" href={`/funding?transferId=${transfer.id}`}>
            Fund
          </Link>
        ) : (
          <Link className="text-link" href={detailHref}>
            View
          </Link>
        )}
      </td>
    </tr>
  );
}

export default function HistoryPage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const savedSession = getStoredAuthSession();
    setAuthSession(savedSession);

    if (savedSession) {
      loadTransfers(savedSession.token);
    }
  }, []);

  async function loadTransfers(token = authSession?.token) {
    setError("");

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    setLoading(true);

    try {
      const data = await getTransfers(token);
      setTransfers(data);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <div className="shell stack">
        <header className="topbar">
          <div>
            <p className="kicker">Transactions</p>
            <h1>Transaction history</h1>
            <p className="lede">
              Review submitted transfers and their current processing status.
            </p>
            <Link className="text-link" href="/">
              Start a new transfer
            </Link>
          </div>

          <section className="panel stack">
            <h2>Customer account</h2>
            {authSession ? (
              <>
                <p className="muted small">Signed in as {authSession.user.email}</p>
                <button type="button" onClick={() => loadTransfers()}>
                  {loading ? "Loading..." : "Refresh history"}
                </button>
              </>
            ) : (
              <>
                <p className="muted small">Log in to view your transactions.</p>
                <Link href="/login">
                  <button type="button">Log in</button>
                </Link>
              </>
            )}
          </section>
        </header>

        {error ? <pre className="error small">{error}</pre> : null}

        <section className="panel stack">
          <h2>Submitted transactions</h2>

          {loading ? <p className="notice">Loading transaction history...</p> : null}

          {!loading && transfers.length === 0 ? (
            <p className="muted">No transactions found yet.</p>
          ) : null}

          {transfers.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Status</th>
                    <th>Funding</th>
                    <th>Send amount</th>
                    <th>Receive amount</th>
                    <th>Created</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.map((transfer) => (
                    <HistoryRow key={transfer.id} transfer={transfer} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
