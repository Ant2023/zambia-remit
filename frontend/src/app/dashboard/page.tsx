"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { AuthSession, Recipient, SenderProfile, Transfer } from "@/lib/api";
import {
  formatApiError,
  getRecipients,
  getSenderProfile,
  getTransfers,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";

const ACTIVE_TRANSFER_STATUSES = new Set([
  "awaiting_funding",
  "funding_received",
  "under_review",
  "approved",
  "processing_payout",
  "paid_out",
]);

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatMoney(amount: string, currencyCode?: string) {
  const numericAmount = Number(amount);
  const formattedAmount = Number.isFinite(numericAmount)
    ? numericAmount.toLocaleString("en", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    : amount;

  return currencyCode ? `${formattedAmount} ${currencyCode}` : formattedAmount;
}

function getRecipientName(recipient: Recipient) {
  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

function getProfileCompletionPercent(profile: SenderProfile | null) {
  if (!profile) {
    return 0;
  }

  const items = [
    Boolean(profile.first_name && profile.last_name),
    Boolean(profile.phone_number),
    Boolean(profile.country),
    Boolean(
      profile.address_line_1 &&
        profile.city &&
        profile.region &&
        profile.postal_code,
    ),
  ];

  return Math.round((items.filter(Boolean).length / items.length) * 100);
}

function getDashboardFirstName(
  profile: SenderProfile | null,
  authSession: AuthSession | null,
) {
  return (profile?.first_name || authSession?.user.first_name || "").trim();
}

function getTransferAction(transfer: Transfer) {
  if (transfer.status === "awaiting_funding") {
    return {
      href: `/funding?transferId=${transfer.id}`,
      label: "Complete funding",
    };
  }

  return {
    href: `/transfers/${transfer.id}`,
    label: "View details",
  };
}

export default function DashboardPage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<SenderProfile | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const savedSession = getStoredAuthSession();
    setAuthSession(savedSession);

    if (savedSession?.token && !savedSession.user.is_staff) {
      loadDashboard(savedSession.token);
    }
  }, []);

  const activeTransfers = useMemo(
    () =>
      transfers.filter((transfer) =>
        ACTIVE_TRANSFER_STATUSES.has(transfer.status),
      ),
    [transfers],
  );
  const awaitingFundingTransfers = useMemo(
    () =>
      transfers.filter(
        (transfer) =>
          transfer.status === "awaiting_funding" &&
          transfer.funding_status !== "received",
      ),
    [transfers],
  );
  const recentTransfers = transfers.slice(0, 4);
  const recentRecipients = recipients.slice(0, 4);
  const profilePercent = getProfileCompletionPercent(profile);
  const latestTransfer = transfers[0] ?? null;
  const nextAction = getNextAction({
    profile,
    awaitingFundingTransfer: awaitingFundingTransfers[0] ?? null,
    recipientCount: recipients.length,
  });
  const dashboardFirstName = getDashboardFirstName(profile, authSession);

  async function loadDashboard(token = authSession?.token) {
    setError("");

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    setLoading(true);

    try {
      const [profileData, recipientData, transferData] = await Promise.all([
        getSenderProfile(token),
        getRecipients(token),
        getTransfers(token),
      ]);

      setProfile(profileData);
      setRecipients(recipientData);
      setTransfers(transferData);

      setAuthSession((currentSession) => {
        if (!currentSession) {
          return currentSession;
        }

        const updatedSession = {
          ...currentSession,
          user: {
            ...currentSession.user,
            first_name: profileData.first_name,
            last_name: profileData.last_name,
          },
        };
        saveAuthSession(updatedSession);
        return updatedSession;
      });
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  const isStaff = Boolean(authSession?.user.is_staff);

  return (
    <>
      <AppNavbar />
      <main className="page">
        <div className="shell stack">
          <header className="topbar">
            <div>
              <p className="kicker">Dashboard</p>
              <h1>
                {dashboardFirstName
                  ? `Welcome back, ${dashboardFirstName}`
                  : "Welcome back"}
              </h1>
              <p className="lede">
                See what needs attention, continue a transfer, and keep your
                account ready for the next send.
              </p>
            </div>

            <section className="panel stack">
              <h2>Customer account</h2>
              {authSession ? (
                <>
                  <p className="muted small">Signed in as {authSession.user.email}</p>
                  {!isStaff ? (
                    <button type="button" onClick={() => loadDashboard()}>
                      {loading ? "Loading..." : "Refresh dashboard"}
                    </button>
                  ) : null}
                </>
              ) : (
                <>
                  <p className="muted small">Log in to view your dashboard.</p>
                  <Link href="/login?mode=login&next=/dashboard">
                    <button type="button">Log in</button>
                  </Link>
                </>
              )}
            </section>
          </header>

          {error ? <pre className="error small">{error}</pre> : null}

          {isStaff ? (
            <section className="panel stack">
              <h2>Staff account</h2>
              <p className="muted">
                Operations accounts use the transfer control center.
              </p>
              <Link href="/operations">
                <button type="button">Open operations</button>
              </Link>
            </section>
          ) : null}

          {!authSession ? (
            <section className="panel stack">
              <h2>Your account, in one place</h2>
              <p className="muted">
                Create or log in to a customer account to see transfers,
                recipients, and profile readiness.
              </p>
              <div className="row">
                <Link href="/login?mode=register&next=/dashboard">
                  <button type="button">Create account</button>
                </Link>
                <Link href="/login?mode=login&next=/dashboard">
                  <button type="button" className="secondary-button">
                    Log in
                  </button>
                </Link>
              </div>
            </section>
          ) : null}

          {authSession && !isStaff ? (
            <>
              <section className="dashboard-metrics" aria-label="Account summary">
                <div className="dashboard-metric">
                  <span>Profile</span>
                  <strong>{profilePercent}%</strong>
                  <p>{profile?.is_complete ? "Funding ready" : "Needs details"}</p>
                </div>
                <div className="dashboard-metric">
                  <span>Recipients</span>
                  <strong>{recipients.length}</strong>
                  <p>Saved people</p>
                </div>
                <div className="dashboard-metric">
                  <span>Active</span>
                  <strong>{activeTransfers.length}</strong>
                  <p>Transfers in motion</p>
                </div>
                <div className="dashboard-metric">
                  <span>Funding</span>
                  <strong>{awaitingFundingTransfers.length}</strong>
                  <p>Awaiting payment</p>
                </div>
              </section>

              <div className="dashboard-layout">
                <section className="panel stack">
                  <div>
                    <p className="kicker">Next best action</p>
                    <h2>{nextAction.title}</h2>
                    <p className="muted">{nextAction.body}</p>
                  </div>

                  <div className="dashboard-action-box">
                    <Link href={nextAction.href}>
                      <button type="button">{nextAction.buttonLabel}</button>
                    </Link>
                    <Link className="text-link" href="/history">
                      View transaction history
                    </Link>
                  </div>
                </section>

                <section className="panel stack">
                  <div>
                    <p className="kicker">Latest transfer</p>
                    <h2>{latestTransfer?.reference ?? "No transfers yet"}</h2>
                  </div>

                  {latestTransfer ? (
                    <>
                      <dl className="summary-list">
                        <div>
                          <dt>Status</dt>
                          <dd>{latestTransfer.status_display}</dd>
                        </div>
                        <div>
                          <dt>Send amount</dt>
                          <dd>
                            {formatMoney(
                              latestTransfer.send_amount,
                              latestTransfer.source_currency_details?.code,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>Recipient receives</dt>
                          <dd>
                            {formatMoney(
                              latestTransfer.receive_amount,
                              latestTransfer.destination_currency_details?.code,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>Created</dt>
                          <dd>{formatDate(latestTransfer.created_at)}</dd>
                        </div>
                      </dl>
                      <Link href={getTransferAction(latestTransfer).href}>
                        <button type="button" className="secondary-button">
                          {getTransferAction(latestTransfer).label}
                        </button>
                      </Link>
                    </>
                  ) : (
                    <>
                      <p className="muted">
                        Start your first transfer when you are ready.
                      </p>
                      <Link href="/send?new=1">
                        <button type="button">Send money</button>
                      </Link>
                    </>
                  )}
                </section>
              </div>

              <div className="grid">
                <section className="panel stack">
                  <div className="row between">
                    <div>
                      <p className="kicker">Transfers</p>
                      <h2>Recent activity</h2>
                    </div>
                    <Link className="text-link" href="/history">
                      View all
                    </Link>
                  </div>

                  {loading ? <p className="notice">Loading dashboard...</p> : null}

                  {!loading && recentTransfers.length === 0 ? (
                    <p className="muted">No transfers found yet.</p>
                  ) : null}

                  {recentTransfers.length > 0 ? (
                    <div className="dashboard-list">
                      {recentTransfers.map((transfer) => {
                        const action = getTransferAction(transfer);
                        return (
                          <article key={transfer.id} className="dashboard-list-item">
                            <div>
                              <Link className="text-link" href={`/transfers/${transfer.id}`}>
                                {transfer.reference}
                              </Link>
                              <p>
                                {transfer.status_display} -{" "}
                                {formatDate(transfer.created_at)}
                              </p>
                            </div>
                            <Link href={action.href}>
                              <button type="button" className="table-action-button">
                                {action.label}
                              </button>
                            </Link>
                          </article>
                        );
                      })}
                    </div>
                  ) : null}
                </section>

                <section className="panel stack">
                  <div className="row between">
                    <div>
                      <p className="kicker">Recipients</p>
                      <h2>Saved people</h2>
                    </div>
                    <Link className="text-link" href="/recipients">
                      Manage
                    </Link>
                  </div>

                  {!loading && recentRecipients.length === 0 ? (
                    <p className="muted">No saved recipients yet.</p>
                  ) : null}

                  {recentRecipients.length > 0 ? (
                    <div className="dashboard-list">
                      {recentRecipients.map((recipient) => (
                        <article key={recipient.id} className="dashboard-list-item">
                          <div>
                            <strong>{getRecipientName(recipient)}</strong>
                            <p>
                              {recipient.country.name}
                              {recipient.relationship_to_sender
                                ? ` - ${recipient.relationship_to_sender}`
                                : ""}
                            </p>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : null}

                  <Link href="/send?new=1">
                    <button type="button" className="secondary-button">
                      Add in send flow
                    </button>
                  </Link>
                </section>
              </div>
            </>
          ) : null}
        </div>
      </main>
    </>
  );
}

function getNextAction({
  profile,
  awaitingFundingTransfer,
  recipientCount,
}: {
  profile: SenderProfile | null;
  awaitingFundingTransfer: Transfer | null;
  recipientCount: number;
}) {
  if (!profile?.is_complete) {
    return {
      title: "Complete your profile",
      body: "Add the required sender details once, then future transfers move faster.",
      href: "/profile",
      buttonLabel: "Finish profile",
    };
  }

  if (awaitingFundingTransfer) {
    return {
      title: "Finish funding",
      body: `${awaitingFundingTransfer.reference} is waiting for payment confirmation.`,
      href: `/funding?transferId=${awaitingFundingTransfer.id}`,
      buttonLabel: "Complete funding",
    };
  }

  if (recipientCount === 0) {
    return {
      title: "Add your first recipient",
      body: "Set up who you send to most often, then reuse them in future transfers.",
      href: "/send?new=1",
      buttonLabel: "Add recipient",
    };
  }

  return {
    title: "Start a new transfer",
    body: "Your account is ready. Choose a route, pick a saved recipient, and send.",
    href: "/send?new=1",
    buttonLabel: "Send money",
  };
}
