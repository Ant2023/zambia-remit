"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import { getCustomerStatusLabel } from "@/components/TransferStatusStepper";
import {
  Button,
  Card,
  MobileContainer,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
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

function getTransferStatusTone(transfer: Transfer) {
  if (transfer.status === "failed") {
    return "error" as const;
  }

  if (transfer.status === "paid_out" || transfer.status === "completed") {
    return "success" as const;
  }

  if (transfer.status === "awaiting_funding") {
    return "warning" as const;
  }

  return "info" as const;
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
      <MobileContainer className="max-w-6xl space-y-5 py-6 sm:py-10">
        <PageHeader
          action={
            authSession && !isStaff ? (
              <Button
                disabled={loading}
                fullWidth
                onClick={() => loadDashboard()}
                variant="secondary"
              >
                {loading ? "Loading..." : "Refresh"}
              </Button>
            ) : null
          }
          description="Send money, track transfers, and keep your account ready for the next payout."
          eyebrow="Dashboard"
          title={
            dashboardFirstName
              ? `Welcome back, ${dashboardFirstName}`
              : "Welcome back"
          }
        />

        {error ? (
          <Card className="border-red-200 bg-red-50">
            <pre className="whitespace-pre-wrap text-sm font-semibold text-mbongo-error">
              {error}
            </pre>
          </Card>
        ) : null}

        {isStaff ? (
          <Card className="space-y-4">
            <StatusBadge tone="info">Staff account</StatusBadge>
            <div className="space-y-1">
              <h2 className="text-xl font-bold text-mbongo-navy">
                Operations account
              </h2>
              <p className="mbp-helper-text">
                Operations accounts use the transfer control center.
              </p>
            </div>
            <Link className="mbp-button-primary" href="/operations">
              Open operations
            </Link>
          </Card>
        ) : null}

        {!authSession ? (
          <Card className="space-y-5">
            <div className="space-y-2">
              <StatusBadge tone="info">Customer account</StatusBadge>
              <h2 className="text-2xl font-bold text-mbongo-navy">
                Your money transfer home
              </h2>
              <p className="text-sm leading-6 text-mbongo-muted sm:text-base">
                Create or log in to a customer account to see transfers,
                recipients, and profile readiness.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Link className="mbp-button-primary" href="/login?mode=register&next=/dashboard">
                Create account
              </Link>
              <Link className="mbp-button-secondary" href="/login?mode=login&next=/dashboard">
                Log in
              </Link>
            </div>
          </Card>
        ) : null}

        {authSession && !isStaff ? (
          <>
            <Card className="overflow-hidden bg-mbongo-navy p-0 text-white">
              <div className="space-y-5 p-5 sm:p-6">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-2">
                    <StatusBadge className="bg-white/10 text-white ring-white/20" tone="info">
                      Customer account
                    </StatusBadge>
                    <h2 className="text-2xl font-bold leading-tight">
                      Ready to send?
                    </h2>
                    <p className="max-w-2xl text-sm leading-6 text-white/80 sm:text-base">
                      Start a transfer, continue funding, or review your latest
                      activity from one place.
                    </p>
                  </div>
                  <p className="text-sm font-semibold text-white/70">
                    {authSession.user.email}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <Link className="mbp-button-accent min-h-14 text-base" href="/send?new=1">
                    Send money
                  </Link>
                  <Link className="mbp-button-secondary min-h-14 border-white/20 bg-white/10 text-base text-white hover:bg-white/15" href="/history">
                    View transfers
                  </Link>
                </div>
              </div>
            </Card>

            <section
              aria-label="Account summary"
              className="grid grid-cols-2 gap-3 lg:grid-cols-4"
            >
              <Card className="space-y-1 p-4">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-mbongo-muted">
                  Profile
                </span>
                <strong className="block text-2xl font-bold text-mbongo-navy">
                  {profilePercent}%
                </strong>
                <p className="text-sm text-mbongo-muted">
                  {profile?.is_complete ? "Funding ready" : "Needs details"}
                </p>
              </Card>
              <Card className="space-y-1 p-4">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-mbongo-muted">
                  Recipients
                </span>
                <strong className="block text-2xl font-bold text-mbongo-navy">
                  {recipients.length}
                </strong>
                <p className="text-sm text-mbongo-muted">Saved people</p>
              </Card>
              <Card className="space-y-1 p-4">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-mbongo-muted">
                  Active
                </span>
                <strong className="block text-2xl font-bold text-mbongo-navy">
                  {activeTransfers.length}
                </strong>
                <p className="text-sm text-mbongo-muted">Transfers in motion</p>
              </Card>
              <Card className="space-y-1 p-4">
                <span className="text-xs font-bold uppercase tracking-[0.12em] text-mbongo-muted">
                  Funding
                </span>
                <strong className="block text-2xl font-bold text-mbongo-navy">
                  {awaitingFundingTransfers.length}
                </strong>
                <p className="text-sm text-mbongo-muted">Awaiting payment</p>
              </Card>
            </section>

            <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
              <Card className="space-y-5">
                <div className="space-y-2">
                  <p className="mbp-page-kicker">Next best action</p>
                  <h2 className="text-xl font-bold text-mbongo-navy">
                    {nextAction.title}
                  </h2>
                  <p className="text-sm leading-6 text-mbongo-muted">
                    {nextAction.body}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                  <Link className="mbp-button-primary" href={nextAction.href}>
                    {nextAction.buttonLabel}
                  </Link>
                  <Link className="mbp-button-secondary" href="/history">
                    Transaction history
                  </Link>
                </div>
              </Card>

              <Card className="space-y-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="mbp-page-kicker">Latest transfer</p>
                    <h2 className="text-xl font-bold text-mbongo-navy">
                      {latestTransfer?.reference ?? "No transfers yet"}
                    </h2>
                  </div>
                  {latestTransfer ? (
                    <StatusBadge tone={getTransferStatusTone(latestTransfer)}>
                      {getCustomerStatusLabel(latestTransfer)}
                    </StatusBadge>
                  ) : null}
                </div>

                {latestTransfer ? (
                  <>
                    <dl className="grid gap-3 text-sm">
                      <div className="flex items-center justify-between gap-4 border-b border-mbongo-line pb-3">
                        <dt className="text-mbongo-muted">Send amount</dt>
                        <dd className="font-bold text-mbongo-navy">
                          {formatMoney(
                            latestTransfer.send_amount,
                            latestTransfer.source_currency_details?.code,
                          )}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-4 border-b border-mbongo-line pb-3">
                        <dt className="text-mbongo-muted">Recipient receives</dt>
                        <dd className="font-bold text-mbongo-navy">
                          {formatMoney(
                            latestTransfer.receive_amount,
                            latestTransfer.destination_currency_details?.code,
                          )}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <dt className="text-mbongo-muted">Created</dt>
                        <dd className="font-bold text-mbongo-navy">
                          {formatDate(latestTransfer.created_at)}
                        </dd>
                      </div>
                    </dl>
                    <Link
                      className="mbp-button-secondary"
                      href={getTransferAction(latestTransfer).href}
                    >
                      {getTransferAction(latestTransfer).label}
                    </Link>
                  </>
                ) : (
                  <>
                    <p className="text-sm leading-6 text-mbongo-muted">
                      Start your first transfer when you are ready.
                    </p>
                    <Link className="mbp-button-primary" href="/send?new=1">
                      Send money
                    </Link>
                  </>
                )}
              </Card>
            </div>

            <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
              <Card className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="mbp-page-kicker">Transfers</p>
                    <h2 className="text-xl font-bold text-mbongo-navy">
                      Recent activity
                    </h2>
                  </div>
                  <Link className="text-sm font-bold text-mbongo-teal" href="/history">
                    View all
                  </Link>
                </div>

                {loading ? (
                  <p className="rounded-lg bg-mbongo-teal-soft px-4 py-3 text-sm font-semibold text-mbongo-navy">
                    Loading dashboard...
                  </p>
                ) : null}

                {!loading && recentTransfers.length === 0 ? (
                  <p className="text-sm text-mbongo-muted">No transfers found yet.</p>
                ) : null}

                {recentTransfers.length > 0 ? (
                  <div className="grid gap-3">
                    {recentTransfers.map((transfer) => {
                      const action = getTransferAction(transfer);
                      return (
                        <article
                          className="grid gap-3 rounded-lg border border-mbongo-line bg-white p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                          key={transfer.id}
                        >
                          <div className="min-w-0 space-y-1">
                            <Link
                              className="font-bold text-mbongo-navy"
                              href={`/transfers/${transfer.id}`}
                            >
                              {transfer.reference}
                            </Link>
                            <p className="text-sm text-mbongo-muted">
                              {getCustomerStatusLabel(transfer)} ·{" "}
                              {formatDate(transfer.created_at)}
                            </p>
                          </div>
                          <Link className="mbp-button-secondary min-h-10 py-2" href={action.href}>
                            {action.label}
                          </Link>
                        </article>
                      );
                    })}
                  </div>
                ) : null}
              </Card>

              <Card className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="mbp-page-kicker">Recipients</p>
                    <h2 className="text-xl font-bold text-mbongo-navy">
                      Saved people
                    </h2>
                  </div>
                  <Link className="text-sm font-bold text-mbongo-teal" href="/recipients">
                    Manage
                  </Link>
                </div>

                {!loading && recentRecipients.length === 0 ? (
                  <p className="text-sm text-mbongo-muted">No saved recipients yet.</p>
                ) : null}

                {recentRecipients.length > 0 ? (
                  <div className="grid gap-3">
                    {recentRecipients.map((recipient) => (
                      <article
                        className="rounded-lg border border-mbongo-line bg-white p-4"
                        key={recipient.id}
                      >
                        <strong className="block text-mbongo-navy">
                          {getRecipientName(recipient)}
                        </strong>
                        <p className="mt-1 text-sm text-mbongo-muted">
                          {recipient.country.name}
                          {recipient.relationship_to_sender
                            ? ` · ${recipient.relationship_to_sender}`
                            : ""}
                        </p>
                      </article>
                    ))}
                  </div>
                ) : null}

                <Link className="mbp-button-secondary" href="/send?new=1">
                  Add in send flow
                </Link>
              </Card>
            </div>

            <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-lg font-bold text-mbongo-navy">
                  Need help with a transfer?
                </h2>
                <p className="mt-1 text-sm text-mbongo-muted">
                  Find support answers or contact the team with your reference.
                </p>
              </div>
              <Link className="mbp-button-secondary" href="/help">
                Help center
              </Link>
            </Card>
          </>
        ) : null}
      </MobileContainer>
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
