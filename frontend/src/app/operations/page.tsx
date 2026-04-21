"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { AuthSession, OperationalTransfer } from "@/lib/api";
import {
  applyTransferComplianceAction,
  formatApiError,
  getCurrentUser,
  getOperationalTransfers,
  loginStaff,
  reviewTransferAmlFlag,
  reviewTransferSanctionsCheck,
  transitionTransferStatus,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";

const STATUS_FILTERS = [
  { value: "", label: "All transfers" },
  { value: "funding_received", label: "Funding received" },
  { value: "under_review", label: "Under review" },
  { value: "approved", label: "Approved" },
  { value: "processing_payout", label: "Processing payout" },
  { value: "paid_out", label: "Paid out" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "rejected", label: "Rejected" },
  { value: "refunded", label: "Refunded" },
];

const ACTIVE_STATUSES = new Set([
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
    hour: "numeric",
    minute: "2-digit",
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

function getRecipientName(transfer: OperationalTransfer) {
  const recipient = transfer.recipient_details;
  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

function getMetadataString(
  metadata: Record<string, unknown>,
  key: string,
): string {
  const value = metadata[key];
  return typeof value === "string" ? value : "";
}

function getStatusTone(status: string) {
  if (["completed", "paid_out", "approved"].includes(status)) {
    return "success";
  }

  if (["failed", "rejected", "cancelled"].includes(status)) {
    return "danger";
  }

  if (["funding_received", "under_review", "processing_payout"].includes(status)) {
    return "warning";
  }

  return "neutral";
}

function QueueRow({
  transfer,
  isSelected,
  onSelect,
}: {
  transfer: OperationalTransfer;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <tr className={isSelected ? "selected-row" : ""}>
      <td>
        <button
          type="button"
          className="link-button"
          onClick={onSelect}
        >
          {transfer.reference}
        </button>
      </td>
      <td>
        <span className="status-pill" data-tone={getStatusTone(transfer.status)}>
          {transfer.status_display}
        </span>
      </td>
      <td>{transfer.sender_email}</td>
      <td>{getRecipientName(transfer)}</td>
      <td>
        {formatMoney(
          transfer.send_amount,
          transfer.source_currency_details?.code,
        )}
      </td>
      <td>{formatDate(transfer.created_at)}</td>
      <td>{transfer.compliance_flags.length}</td>
      <td>{transfer.allowed_next_statuses.length}</td>
    </tr>
  );
}

export default function OperationsPage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [transfers, setTransfers] = useState<OperationalTransfer[]>([]);
  const [selectedTransfer, setSelectedTransfer] =
    useState<OperationalTransfer | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [transitionStatus, setTransitionStatus] = useState("");
  const [transitionNote, setTransitionNote] = useState("");
  const [complianceAction, setComplianceAction] = useState("note");
  const [complianceNote, setComplianceNote] = useState("");
  const [selectedAmlFlagId, setSelectedAmlFlagId] = useState("");
  const [amlDecision, setAmlDecision] = useState("acknowledge");
  const [amlNote, setAmlNote] = useState("");
  const [amlEscalationDestination, setAmlEscalationDestination] = useState("");
  const [amlEscalationReference, setAmlEscalationReference] = useState("");
  const [selectedSanctionsCheckId, setSelectedSanctionsCheckId] = useState("");
  const [sanctionsStatus, setSanctionsStatus] = useState("clear");
  const [sanctionsNote, setSanctionsNote] = useState("");
  const [sanctionsProviderReference, setSanctionsProviderReference] = useState("");
  const [sanctionsMatchScore, setSanctionsMatchScore] = useState("");
  const [loading, setLoading] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [applyingCompliance, setApplyingCompliance] = useState(false);
  const [reviewingAml, setReviewingAml] = useState(false);
  const [reviewingSanctions, setReviewingSanctions] = useState(false);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  useEffect(() => {
    const savedSession = getStoredAuthSession();
    setAuthSession(savedSession);

    if (savedSession?.user.is_staff) {
      loadTransfers(savedSession.token);
    }
  }, []);

  useEffect(() => {
    const nextStatus = selectedTransfer?.allowed_next_statuses[0]?.status ?? "";
    setTransitionStatus(nextStatus);
    setTransitionNote("");
    setComplianceAction("note");
    setComplianceNote("");
    setSelectedAmlFlagId(
      selectedTransfer?.compliance_flags.find((flag) => flag.category === "aml")?.id ??
        "",
    );
    setAmlDecision("acknowledge");
    setAmlNote("");
    setAmlEscalationDestination("");
    setAmlEscalationReference("");
    setSelectedSanctionsCheckId(selectedTransfer?.sanctions_checks[0]?.id ?? "");
    setSanctionsStatus("clear");
    setSanctionsNote("");
    setSanctionsProviderReference("");
    setSanctionsMatchScore("");
  }, [selectedTransfer?.id, selectedTransfer?.status]);

  const metrics = useMemo(() => {
    return {
      active: transfers.filter((transfer) => ACTIVE_STATUSES.has(transfer.status))
        .length,
      review: transfers.filter((transfer) =>
        ["funding_received", "under_review"].includes(transfer.status),
      ).length,
      payout: transfers.filter((transfer) =>
        ["approved", "processing_payout", "paid_out"].includes(transfer.status),
      ).length,
      exceptions: transfers.filter((transfer) =>
        ["failed", "rejected", "refunded"].includes(transfer.status),
      ).length,
    };
  }, [transfers]);

  async function loadTransfers(token = authSession?.token) {
    setError("");
    setActionMessage("");

    if (!token) {
      setError("Sign in with a staff account first.");
      return;
    }

    setLoading(true);

    try {
      const data = await getOperationalTransfers(token, {
        status: statusFilter,
        q: searchTerm.trim(),
      });
      setTransfers(data);
      setSelectedTransfer((currentTransfer) => {
        if (!currentTransfer) {
          return data[0] ?? null;
        }

        return (
          data.find((transfer) => transfer.id === currentTransfer.id) ??
          data[0] ??
          null
        );
      });
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  async function handleStaffLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setActionMessage("");
    setSigningIn(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");

    try {
      const session = await loginStaff({ email, password });
      const user = await getCurrentUser(session.token);

      if (!user.is_staff) {
        throw new Error("Staff access is required.");
      }

      const staffSession = { token: session.token, user };
      saveAuthSession(staffSession);
      setAuthSession(staffSession);
      await loadTransfers(staffSession.token);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSigningIn(false);
    }
  }

  function handleQueueSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loadTransfers();
  }

  async function handleTransition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setActionMessage("");

    if (!authSession?.token || !selectedTransfer || !transitionStatus) {
      return;
    }

    setTransitioning(true);

    try {
      const updatedTransfer = await transitionTransferStatus(
        selectedTransfer.id,
        {
          status: transitionStatus,
          note: transitionNote.trim(),
        },
        authSession.token,
      );
      const refreshedTransfers = await getOperationalTransfers(authSession.token, {
        status: statusFilter,
        q: searchTerm.trim(),
      });

      setTransfers(refreshedTransfers);
      setSelectedTransfer(
        refreshedTransfers.find((transfer) => transfer.id === updatedTransfer.id) ??
          updatedTransfer,
      );
      setActionMessage(
        `${updatedTransfer.reference} moved to ${updatedTransfer.status_display}.`,
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setTransitioning(false);
    }
  }

  async function handleComplianceAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setActionMessage("");

    if (!authSession?.token || !selectedTransfer) {
      return;
    }

    setApplyingCompliance(true);

    try {
      const updatedTransfer = await applyTransferComplianceAction(
        selectedTransfer.id,
        {
          action: complianceAction,
          note: complianceNote.trim(),
        },
        authSession.token,
      );
      const refreshedTransfers = await getOperationalTransfers(authSession.token, {
        status: statusFilter,
        q: searchTerm.trim(),
      });

      setTransfers(refreshedTransfers);
      setSelectedTransfer(
        refreshedTransfers.find((transfer) => transfer.id === updatedTransfer.id) ??
          updatedTransfer,
      );
      setComplianceNote("");
      setActionMessage(
        `${updatedTransfer.reference} compliance action recorded.`,
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setApplyingCompliance(false);
    }
  }

  async function handleAmlReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setActionMessage("");

    if (!authSession?.token || !selectedTransfer || !selectedAmlFlagId) {
      return;
    }

    setReviewingAml(true);

    try {
      const updatedTransfer = await reviewTransferAmlFlag(
        selectedTransfer.id,
        selectedAmlFlagId,
        {
          decision: amlDecision,
          review_note: amlNote.trim(),
          escalation_destination: amlEscalationDestination.trim(),
          escalation_reference: amlEscalationReference.trim(),
        },
        authSession.token,
      );
      const refreshedTransfers = await getOperationalTransfers(authSession.token, {
        status: statusFilter,
        q: searchTerm.trim(),
      });

      setTransfers(refreshedTransfers);
      setSelectedTransfer(
        refreshedTransfers.find((transfer) => transfer.id === updatedTransfer.id) ??
          updatedTransfer,
      );
      setActionMessage(`${updatedTransfer.reference} AML alert updated.`);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setReviewingAml(false);
    }
  }

  async function handleSanctionsReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setActionMessage("");

    if (!authSession?.token || !selectedTransfer || !selectedSanctionsCheckId) {
      return;
    }

    setReviewingSanctions(true);

    try {
      const updatedTransfer = await reviewTransferSanctionsCheck(
        selectedTransfer.id,
        selectedSanctionsCheckId,
        {
          status: sanctionsStatus,
          review_note: sanctionsNote.trim(),
          provider_reference: sanctionsProviderReference.trim(),
          match_score: sanctionsMatchScore.trim() || null,
        },
        authSession.token,
      );
      const refreshedTransfers = await getOperationalTransfers(authSession.token, {
        status: statusFilter,
        q: searchTerm.trim(),
      });

      setTransfers(refreshedTransfers);
      setSelectedTransfer(
        refreshedTransfers.find((transfer) => transfer.id === updatedTransfer.id) ??
          updatedTransfer,
      );
      setSanctionsNote("");
      setSanctionsMatchScore("");
      setActionMessage(
        `${updatedTransfer.reference} sanctions screening updated.`,
      );
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setReviewingSanctions(false);
    }
  }

  const isStaff = Boolean(authSession?.user.is_staff);
  const allowedNextStatuses = selectedTransfer?.allowed_next_statuses ?? [];
  const amlFlags =
    selectedTransfer?.compliance_flags.filter((flag) => flag.category === "aml") ?? [];
  const selectedAmlFlag =
    amlFlags.find((flag) => flag.id === selectedAmlFlagId) ?? amlFlags[0];
  const selectedSanctionsCheck =
    selectedTransfer?.sanctions_checks.find(
      (check) => check.id === selectedSanctionsCheckId,
    ) ?? selectedTransfer?.sanctions_checks[0];

  useEffect(() => {
    if (!selectedAmlFlag) {
      return;
    }

    const workflowStatus = getMetadataString(
      selectedAmlFlag.metadata,
      "aml_workflow_status",
    );
    const nextDecision =
      workflowStatus === "under_review"
        ? "review"
        : workflowStatus === "escalated"
          ? "escalate"
          : workflowStatus === "cleared"
            ? "clear"
            : workflowStatus === "dismissed"
              ? "dismiss"
              : workflowStatus === "reported"
                ? "report"
                : "acknowledge";

    setAmlDecision(nextDecision);
    setAmlNote(getMetadataString(selectedAmlFlag.metadata, "review_note"));
    setAmlEscalationDestination(
      getMetadataString(selectedAmlFlag.metadata, "escalation_destination"),
    );
    setAmlEscalationReference(
      getMetadataString(selectedAmlFlag.metadata, "escalation_reference"),
    );
  }, [selectedAmlFlag?.id]);

  useEffect(() => {
    if (!selectedSanctionsCheck) {
      return;
    }

    setSanctionsStatus(
      selectedSanctionsCheck.status === "queued"
        ? "clear"
        : selectedSanctionsCheck.status,
    );
    setSanctionsNote(selectedSanctionsCheck.review_note);
    setSanctionsProviderReference(selectedSanctionsCheck.provider_reference);
    setSanctionsMatchScore(selectedSanctionsCheck.match_score ?? "");
  }, [selectedSanctionsCheck?.id]);

  return (
    <>
      <AppNavbar />
      <main className="page">
        <div className="shell stack">
          <header className="topbar">
            <div>
              <p className="kicker">Operations</p>
              <h1>Transfer control center</h1>
              <p className="lede">
                Review funded transfers, move approved payouts forward, and keep
                a clean status trail for every customer.
              </p>
            </div>

            <section className="panel stack">
              <h2>Staff access</h2>
              {isStaff ? (
                <>
                  <p className="muted small">Signed in as {authSession?.user.email}</p>
                  <button type="button" onClick={() => loadTransfers()}>
                    {loading ? "Loading..." : "Refresh queue"}
                  </button>
                </>
              ) : (
                <p className="muted small">
                  Sign in with a staff account to manage transfer operations.
                </p>
              )}
            </section>
          </header>

          {error ? <pre className="error small">{error}</pre> : null}
          {actionMessage ? <p className="success small">{actionMessage}</p> : null}

          {!isStaff ? (
            <section className="panel stack operations-login-panel">
              <h2>Staff sign in</h2>
              {authSession ? (
                <p className="notice small">
                  {authSession.user.email} is signed in as a customer. Staff
                  credentials are required here.
                </p>
              ) : null}

              <form className="auth-form" onSubmit={handleStaffLogin}>
                <label>
                  Email
                  <input name="email" type="email" autoComplete="email" required />
                </label>

                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    minLength={8}
                    required
                  />
                </label>

                <button type="submit" disabled={signingIn}>
                  {signingIn ? "Signing in..." : "Open operations"}
                </button>
              </form>
            </section>
          ) : (
            <>
              <section className="operations-metrics" aria-label="Queue summary">
                <div className="operations-metric">
                  <span>Active</span>
                  <strong>{metrics.active}</strong>
                </div>
                <div className="operations-metric">
                  <span>Review</span>
                  <strong>{metrics.review}</strong>
                </div>
                <div className="operations-metric">
                  <span>Payout</span>
                  <strong>{metrics.payout}</strong>
                </div>
                <div className="operations-metric">
                  <span>Exceptions</span>
                  <strong>{metrics.exceptions}</strong>
                </div>
              </section>

              <div className="operations-layout">
                <section className="panel stack">
                  <div>
                    <p className="kicker">Work queue</p>
                    <h2>Transfer reviews</h2>
                  </div>

                  <form className="operations-filter" onSubmit={handleQueueSubmit}>
                    <label>
                      Search
                      <input
                        value={searchTerm}
                        onChange={(event) => setSearchTerm(event.target.value)}
                        placeholder="Reference, sender, recipient, phone"
                      />
                    </label>

                    <label>
                      Status
                      <select
                        value={statusFilter}
                        onChange={(event) => setStatusFilter(event.target.value)}
                      >
                        {STATUS_FILTERS.map((filter) => (
                          <option key={filter.value || "all"} value={filter.value}>
                            {filter.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <button type="submit" disabled={loading}>
                      {loading ? "Loading..." : "Apply"}
                    </button>
                  </form>

                  {loading ? (
                    <p className="notice">Loading operations queue...</p>
                  ) : null}

                  {!loading && transfers.length === 0 ? (
                    <p className="muted">No transfers match this queue.</p>
                  ) : null}

                  {transfers.length > 0 ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Reference</th>
                            <th>Status</th>
                            <th>Sender</th>
                            <th>Recipient</th>
                            <th>Send amount</th>
                            <th>Created</th>
                            <th>Flags</th>
                            <th>Next</th>
                          </tr>
                        </thead>
                        <tbody>
                          {transfers.map((transfer) => (
                            <QueueRow
                              key={transfer.id}
                              transfer={transfer}
                              isSelected={selectedTransfer?.id === transfer.id}
                              onSelect={() => setSelectedTransfer(transfer)}
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </section>

                <aside className="panel stack">
                  <div>
                    <p className="kicker">Case file</p>
                    <h2>{selectedTransfer?.reference ?? "Select a transfer"}</h2>
                  </div>

                  {selectedTransfer ? (
                    <>
                      <dl className="summary-list">
                        <div>
                          <dt>Status</dt>
                          <dd>{selectedTransfer.status_display}</dd>
                        </div>
                        <div>
                          <dt>Funding</dt>
                          <dd>{selectedTransfer.funding_status_display}</dd>
                        </div>
                        <div>
                          <dt>Compliance</dt>
                          <dd>{selectedTransfer.compliance_status_display}</dd>
                        </div>
                        <div>
                          <dt>Payout</dt>
                          <dd>{selectedTransfer.payout_status_display}</dd>
                        </div>
                        <div>
                          <dt>Sender</dt>
                          <dd>{selectedTransfer.sender_email}</dd>
                        </div>
                        <div>
                          <dt>Recipient</dt>
                          <dd>{getRecipientName(selectedTransfer)}</dd>
                        </div>
                        <div>
                          <dt>Recipient verification</dt>
                          <dd>
                            {selectedTransfer.recipient_details.verification_status_display}
                          </dd>
                        </div>
                        <div>
                          <dt>Route</dt>
                          <dd>
                            {selectedTransfer.source_country_details.iso_code} to{" "}
                            {selectedTransfer.destination_country_details.iso_code}
                          </dd>
                        </div>
                        <div>
                          <dt>Recipient receives</dt>
                          <dd>
                            {formatMoney(
                              selectedTransfer.receive_amount,
                              selectedTransfer.destination_currency_details?.code,
                            )}
                          </dd>
                        </div>
                      </dl>

                      <section className="stack">
                        <h3>Compliance flags</h3>
                        {selectedTransfer.compliance_flags.length ? (
                          <div className="compliance-flag-list">
                            {selectedTransfer.compliance_flags.map((flag) => (
                              <article
                                key={flag.id}
                                className="compliance-flag-item"
                                data-severity={flag.severity}
                              >
                                <div>
                                  <strong>{flag.title}</strong>
                                  <p>
                                    {flag.category_display} -{" "}
                                    {flag.severity_display} -{" "}
                                    {flag.status_display}
                                  </p>
                                </div>
                                <span>{flag.code}</span>
                              </article>
                            ))}
                          </div>
                        ) : (
                          <p className="muted small">
                            No compliance flags are attached to this transfer.
                          </p>
                        )}
                      </section>

                      <section className="stack">
                        <h3>AML monitoring</h3>
                        {amlFlags.length ? (
                          <>
                            <div className="compliance-flag-list">
                              {amlFlags.map((flag) => (
                                <article
                                  key={flag.id}
                                  className="compliance-flag-item"
                                  data-severity={flag.severity}
                                >
                                  <div>
                                    <strong>{flag.title}</strong>
                                    <p>
                                      {flag.severity_display} - {flag.status_display}
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    className="table-action-button"
                                    onClick={() => setSelectedAmlFlagId(flag.id)}
                                  >
                                    Review
                                  </button>
                                </article>
                              ))}
                            </div>

                            {selectedAmlFlag ? (
                              <form className="stack" onSubmit={handleAmlReview}>
                                <label>
                                  Alert
                                  <select
                                    value={selectedAmlFlagId}
                                    onChange={(event) =>
                                      setSelectedAmlFlagId(event.target.value)
                                    }
                                  >
                                    {amlFlags.map((flag) => (
                                      <option key={flag.id} value={flag.id}>
                                        {flag.code}
                                      </option>
                                    ))}
                                  </select>
                                </label>

                                <label>
                                  Decision
                                  <select
                                    value={amlDecision}
                                    onChange={(event) =>
                                      setAmlDecision(event.target.value)
                                    }
                                  >
                                    <option value="acknowledge">Acknowledge</option>
                                    <option value="review">Mark under review</option>
                                    <option value="escalate">Escalate</option>
                                    <option value="clear">Clear</option>
                                    <option value="dismiss">Dismiss</option>
                                    <option value="report">Mark reported</option>
                                  </select>
                                </label>

                                <label>
                                  Escalation destination
                                  <input
                                    value={amlEscalationDestination}
                                    onChange={(event) =>
                                      setAmlEscalationDestination(event.target.value)
                                    }
                                    placeholder="Internal queue, MLRO, partner bank"
                                  />
                                </label>

                                <label>
                                  Escalation reference
                                  <input
                                    value={amlEscalationReference}
                                    onChange={(event) =>
                                      setAmlEscalationReference(event.target.value)
                                    }
                                    placeholder="Case or report reference"
                                  />
                                </label>

                                <label>
                                  AML note
                                  <textarea
                                    value={amlNote}
                                    onChange={(event) => setAmlNote(event.target.value)}
                                    maxLength={1000}
                                    rows={4}
                                    placeholder="Add investigation context, rationale, or filing notes"
                                  />
                                </label>

                                <button type="submit" disabled={reviewingAml}>
                                  {reviewingAml ? "Saving..." : "Save AML update"}
                                </button>
                              </form>
                            ) : null}
                          </>
                        ) : (
                          <p className="muted small">
                            No AML monitoring alerts are attached to this transfer.
                          </p>
                        )}
                      </section>

                      <section className="stack">
                        <h3>Sanctions screening</h3>
                        {selectedTransfer.sanctions_checks.length ? (
                          <>
                            <div className="compliance-flag-list">
                              {selectedTransfer.sanctions_checks.map((check) => (
                                <article
                                  key={check.id}
                                  className="compliance-flag-item"
                                  data-severity={
                                    check.status === "confirmed_match"
                                      ? "critical"
                                      : check.status === "possible_match"
                                        ? "high"
                                        : "low"
                                  }
                                >
                                  <div>
                                    <strong>{check.party_type_display}</strong>
                                    <p>
                                      {check.status_display} - {check.screened_name}
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    className="table-action-button"
                                    onClick={() => {
                                      setSelectedSanctionsCheckId(check.id);
                                      setSanctionsProviderReference(
                                        check.provider_reference,
                                      );
                                    }}
                                  >
                                    Review
                                  </button>
                                </article>
                              ))}
                            </div>

                            {selectedSanctionsCheck ? (
                              <form className="stack" onSubmit={handleSanctionsReview}>
                                <label>
                                  Screening target
                                  <select
                                    value={selectedSanctionsCheckId}
                                    onChange={(event) =>
                                      setSelectedSanctionsCheckId(event.target.value)
                                    }
                                  >
                                    {selectedTransfer.sanctions_checks.map((check) => (
                                      <option key={check.id} value={check.id}>
                                        {check.party_type_display}
                                      </option>
                                    ))}
                                  </select>
                                </label>

                                <label>
                                  Result
                                  <select
                                    value={sanctionsStatus}
                                    onChange={(event) =>
                                      setSanctionsStatus(event.target.value)
                                    }
                                  >
                                    <option value="clear">Clear</option>
                                    <option value="possible_match">
                                      Possible match
                                    </option>
                                    <option value="confirmed_match">
                                      Confirmed match
                                    </option>
                                    <option value="error">Error</option>
                                    <option value="skipped">Skipped</option>
                                  </select>
                                </label>

                                <label>
                                  Provider reference
                                  <input
                                    value={sanctionsProviderReference}
                                    onChange={(event) =>
                                      setSanctionsProviderReference(
                                        event.target.value,
                                      )
                                    }
                                    placeholder="Vendor case or screening reference"
                                  />
                                </label>

                                <label>
                                  Match score
                                  <input
                                    value={sanctionsMatchScore}
                                    onChange={(event) =>
                                      setSanctionsMatchScore(event.target.value)
                                    }
                                    placeholder="Optional score"
                                  />
                                </label>

                                <label>
                                  Screening note
                                  <textarea
                                    value={sanctionsNote}
                                    onChange={(event) =>
                                      setSanctionsNote(event.target.value)
                                    }
                                    maxLength={1000}
                                    rows={4}
                                    placeholder="Add screening rationale, false-positive notes, or escalation context"
                                  />
                                </label>

                                <button type="submit" disabled={reviewingSanctions}>
                                  {reviewingSanctions
                                    ? "Saving..."
                                    : "Save screening result"}
                                </button>
                              </form>
                            ) : null}
                          </>
                        ) : (
                          <p className="muted small">
                            No sanctions checks have been queued yet.
                          </p>
                        )}
                      </section>

                      <section className="stack">
                        <h3>Compliance actions</h3>
                        <form className="stack" onSubmit={handleComplianceAction}>
                          <label>
                            Action
                            <select
                              value={complianceAction}
                              onChange={(event) =>
                                setComplianceAction(event.target.value)
                              }
                            >
                              <option value="note">Add note</option>
                              <option value="hold">Put on hold</option>
                              <option value="review">Start review</option>
                              <option value="approve">Approve compliance</option>
                              <option value="reject">Reject transfer</option>
                            </select>
                          </label>

                          <label>
                            Note
                            <textarea
                              value={complianceNote}
                              onChange={(event) =>
                                setComplianceNote(event.target.value)
                              }
                              maxLength={1000}
                              rows={4}
                              placeholder="Add the compliance rationale, escalation, or reviewer note"
                            />
                          </label>

                          <button type="submit" disabled={applyingCompliance}>
                            {applyingCompliance
                              ? "Saving..."
                              : "Record compliance action"}
                          </button>
                        </form>
                      </section>

                      {allowedNextStatuses.length > 0 ? (
                        <form className="stack" onSubmit={handleTransition}>
                          <label>
                            Next status
                            <select
                              value={transitionStatus}
                              onChange={(event) =>
                                setTransitionStatus(event.target.value)
                              }
                            >
                              {allowedNextStatuses.map((option) => (
                                <option key={option.status} value={option.status}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </label>

                          <label>
                            Decision note
                            <textarea
                              value={transitionNote}
                              onChange={(event) =>
                                setTransitionNote(event.target.value)
                              }
                              maxLength={500}
                              rows={4}
                              placeholder="Add the review, payout, or exception note"
                            />
                          </label>

                          <button type="submit" disabled={transitioning}>
                            {transitioning ? "Saving..." : "Apply status change"}
                          </button>
                        </form>
                      ) : (
                        <p className="notice small">
                          No further status actions are available for this transfer.
                        </p>
                      )}

                      <section className="stack">
                        <h3>Compliance activity</h3>
                        {selectedTransfer.compliance_events.length ? (
                          <ol className="event-list">
                            {selectedTransfer.compliance_events.map((event) => (
                              <li key={event.id}>
                                <strong>{event.action_display}</strong>
                                <span>{formatDate(event.created_at)}</span>
                                <p>
                                  {event.from_compliance_status_display
                                    ? `${event.from_compliance_status_display} to `
                                    : ""}
                                  {event.to_compliance_status_display || "No status change"}
                                </p>
                                {event.note ? <p>{event.note}</p> : null}
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="muted small">
                            No compliance activity has been recorded yet.
                          </p>
                        )}
                      </section>

                      <section className="stack">
                        <h3>Status trail</h3>
                        {selectedTransfer.status_events.length ? (
                          <ol className="event-list">
                            {selectedTransfer.status_events.map((event) => (
                              <li key={event.id}>
                                <strong>{event.to_status_display}</strong>
                                <span>{formatDate(event.created_at)}</span>
                                {event.note ? <p>{event.note}</p> : null}
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="muted small">No status events found yet.</p>
                        )}
                      </section>
                    </>
                  ) : (
                    <p className="muted">Choose a transfer from the queue.</p>
                  )}
                </aside>
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}
