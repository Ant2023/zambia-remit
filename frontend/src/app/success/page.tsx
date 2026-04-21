"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { Transfer } from "@/lib/api";
import { getTransfer } from "@/lib/api";
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

function formatProviderName(value?: string) {
  return value ? value.replaceAll("_", " ") : "Not prepared";
}

function formatPayoutMethod(value: Transfer["payout_method"]) {
  return value === "mobile_money" ? "Mobile money" : "Bank deposit";
}

function getRecipientName(transfer: Transfer) {
  const recipient = transfer.recipient_details;
  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

function getPayoutDestination(transfer: Transfer) {
  const mobileAccount = transfer.recipient_details.mobile_money_accounts[0];
  const bankAccount = transfer.recipient_details.bank_accounts[0];

  if (transfer.payout_method === "mobile_money") {
    return mobileAccount
      ? `${mobileAccount.provider_name} - ${mobileAccount.mobile_number}`
      : "Mobile money";
  }

  return bankAccount
    ? `${bankAccount.bank_name} - ${bankAccount.account_number}`
    : "Bank deposit";
}

function getReceiptContent(transfer: Transfer | null) {
  if (!transfer) {
    return {
      kicker: "Transfer receipt",
      title: "Transfer summary",
      description: "The latest transfer summary is not available in this browser.",
    };
  }

  const paymentStatus = transfer.latest_payment_instruction?.status;
  const paymentReason = transfer.latest_payment_instruction?.status_reason;
  const needsFunding =
    transfer.status === "awaiting_funding" && transfer.funding_status !== "received";
  const isRefunded =
    paymentStatus === "refunded" ||
    paymentStatus === "reversed" ||
    transfer.status === "refunded" ||
    transfer.funding_status === "refunded";

  if (paymentStatus === "failed") {
    return {
      kicker: "Payment update",
      title: "Payment failed",
      description:
        paymentReason ||
        `Reference ${transfer.reference} needs another payment attempt.`,
    };
  }

  if (paymentStatus === "requires_review") {
    return {
      kicker: "Payment update",
      title: "Payment under review",
      description:
        paymentReason ||
        `Reference ${transfer.reference} is waiting for processor review.`,
    };
  }

  if (isRefunded) {
    return {
      kicker: "Payment update",
      title: "Payment refunded",
      description:
        paymentReason ||
        `Reference ${transfer.reference} has been moved to a refunded state.`,
    };
  }

  if (paymentStatus === "authorized" && transfer.funding_status !== "received") {
    return {
      kicker: "Payment update",
      title: "Payment authorized",
      description: `Reference ${transfer.reference} is authorized and awaiting funding confirmation.`,
    };
  }

  if (needsFunding) {
    return {
      kicker: "Transfer receipt",
      title: "Transfer submitted",
      description: `Reference ${transfer.reference} is now ${transfer.status_display}.`,
    };
  }

  return {
    kicker: "Payment receipt",
    title: "Funding received",
    description: `Reference ${transfer.reference} is now ${transfer.status_display}.`,
  };
}

export default function SuccessPage() {
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const transferId = params.get("transferId");
    const authSession = getStoredAuthSession();
    const savedTransfer = window.sessionStorage.getItem("latestTransfer");

    if (savedTransfer) {
      const parsedTransfer = JSON.parse(savedTransfer) as Partial<Transfer>;
      if (parsedTransfer.recipient_details && parsedTransfer.source_currency_details) {
        setTransfer(parsedTransfer as Transfer);
      }
    }

    if (transferId && authSession?.token) {
      getTransfer(transferId, authSession.token)
        .then((data) => {
          setTransfer(data);
          window.sessionStorage.setItem("latestTransfer", JSON.stringify(data));
        })
        .catch(() => {
          setError("Could not refresh this receipt.");
        });
    }
  }, []);

  const needsFunding =
    transfer?.status === "awaiting_funding" &&
    transfer?.funding_status !== "received";
  const paymentStatus = transfer?.latest_payment_instruction?.status ?? "";
  const receiptContent = getReceiptContent(transfer);
  const returnToFunding =
    needsFunding ||
    paymentStatus === "authorized" ||
    paymentStatus === "failed" ||
    paymentStatus === "requires_review";

  const totalAmount = useMemo(() => {
    if (!transfer) {
      return "";
    }

    return (Number(transfer.send_amount) + Number(transfer.fee_amount)).toFixed(2);
  }, [transfer]);

  return (
    <>
      <AppNavbar />
      <main className="receipt-page">
        <section className="receipt-card stack">
          <div className="receipt-header">
            <div>
              <p className="kicker">{receiptContent.kicker}</p>
              <h1>{receiptContent.title}</h1>
              <p className="lede">{receiptContent.description}</p>
            </div>

            {transfer ? (
              <div className="receipt-reference">
                <span>Reference</span>
                <strong>{transfer.reference}</strong>
              </div>
            ) : null}
          </div>

          {error ? <p className="notice small">{error}</p> : null}
          {transfer?.latest_payment_instruction?.status_reason ? (
            <p
              className={
                transfer.latest_payment_instruction.status === "failed"
                  ? "error small"
                  : "notice small"
              }
            >
              {transfer.latest_payment_instruction.status_reason}
            </p>
          ) : null}

          {transfer ? (
            <>
              <div className="receipt-status-grid">
                <div>
                  <span>Status</span>
                  <strong>{transfer.status_display}</strong>
                </div>
                <div>
                  <span>Funding</span>
                  <strong>{transfer.funding_status_display}</strong>
                </div>
                <div>
                  <span>Compliance</span>
                  <strong>{transfer.compliance_status_display}</strong>
                </div>
                <div>
                  <span>Payout</span>
                  <strong>{transfer.payout_status_display}</strong>
                </div>
              </div>

              <div className="receipt-grid">
                <section className="receipt-panel stack">
                  <h2>Transfer details</h2>
                  <dl className="summary-list">
                    <div>
                      <dt>Sender</dt>
                      <dd>{transfer.sender_name}</dd>
                    </div>
                    <div>
                      <dt>Sender email</dt>
                      <dd>{transfer.sender_email}</dd>
                    </div>
                    <div>
                      <dt>Recipient</dt>
                      <dd>{getRecipientName(transfer)}</dd>
                    </div>
                    <div>
                      <dt>Recipient phone</dt>
                      <dd>{transfer.recipient_details.phone_number || "Not provided"}</dd>
                    </div>
                    <div>
                      <dt>Route</dt>
                      <dd>
                        {transfer.source_country_details.name} to{" "}
                        {transfer.destination_country_details.name}
                      </dd>
                    </div>
                    <div>
                      <dt>Reason</dt>
                      <dd>{transfer.reason_for_transfer || "Not provided"}</dd>
                    </div>
                  </dl>
                </section>

                <section className="receipt-panel stack">
                  <h2>Amount</h2>
                  <dl className="summary-list">
                    <div>
                      <dt>Send amount</dt>
                      <dd>
                        {transfer.send_amount} {transfer.source_currency_details.code}
                      </dd>
                    </div>
                    <div>
                      <dt>Fee</dt>
                      <dd>
                        {transfer.fee_amount} {transfer.source_currency_details.code}
                      </dd>
                    </div>
                    <div>
                      <dt>Total paid</dt>
                      <dd>
                        {transfer.latest_payment_instruction
                          ? `${transfer.latest_payment_instruction.amount} ${transfer.latest_payment_instruction.currency.code}`
                          : `${totalAmount} ${transfer.source_currency_details.code}`}
                      </dd>
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
                      <dt>Recipient receives</dt>
                      <dd>
                        {transfer.receive_amount}{" "}
                        {transfer.destination_currency_details.code}
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="receipt-panel stack">
                  <h2>Delivery</h2>
                  <dl className="summary-list">
                    <div>
                      <dt>Payout method</dt>
                      <dd>{formatPayoutMethod(transfer.payout_method)}</dd>
                    </div>
                    <div>
                      <dt>Payout details</dt>
                      <dd>{getPayoutDestination(transfer)}</dd>
                    </div>
                    <div>
                      <dt>Destination</dt>
                      <dd>{transfer.destination_country_details.name}</dd>
                    </div>
                  </dl>
                </section>

                <section className="receipt-panel stack">
                  <h2>Payment</h2>
                  <dl className="summary-list">
                    <div>
                      <dt>Method</dt>
                      <dd>
                        {transfer.latest_payment_instruction?.payment_method_display ??
                          "Not prepared"}
                      </dd>
                    </div>
                    <div>
                      <dt>Provider</dt>
                      <dd>
                        {formatProviderName(
                          transfer.latest_payment_instruction?.provider_name,
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Payment reference</dt>
                      <dd>
                        {transfer.latest_payment_instruction?.provider_reference ??
                          "Not prepared"}
                      </dd>
                    </div>
                    <div>
                      <dt>Payment status</dt>
                      <dd>
                        {transfer.latest_payment_instruction?.status_display ??
                          transfer.funding_status_display}
                      </dd>
                    </div>
                    {transfer.latest_payment_instruction?.status_reason ? (
                      <div>
                        <dt>Payment note</dt>
                        <dd>{transfer.latest_payment_instruction.status_reason}</dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>Last payment update</dt>
                      <dd>
                        {transfer.latest_payment_instruction?.refunded_at ??
                          transfer.latest_payment_instruction?.reversed_at ??
                          transfer.latest_payment_instruction?.failed_at ??
                          transfer.latest_payment_instruction?.completed_at ??
                          transfer.latest_payment_instruction?.authorized_at
                            ? formatDate(
                                transfer.latest_payment_instruction?.refunded_at ??
                                  transfer.latest_payment_instruction?.reversed_at ??
                                  transfer.latest_payment_instruction?.failed_at ??
                                  transfer.latest_payment_instruction?.completed_at ??
                                  transfer.latest_payment_instruction?.authorized_at ??
                                  transfer.created_at,
                              )
                            : "Not available"}
                      </dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDate(transfer.created_at)}</dd>
                    </div>
                  </dl>
                </section>
              </div>

              <section className="receipt-panel stack">
                <h2>Timeline</h2>
                {transfer.status_events.length ? (
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

              <div className="receipt-actions">
                {returnToFunding ? (
                  <Link href={`/funding?transferId=${transfer.id}`}>
                    <button type="button">
                      {paymentStatus === "failed"
                        ? "Try payment again"
                        : paymentStatus === "requires_review"
                          ? "Review payment"
                          : "Complete funding"}
                    </button>
                  </Link>
                ) : null}

                <Link href="/send?new=1">
                  <button type="button">Start another transfer</button>
                </Link>

                <Link className="text-link" href={`/transfers/${transfer.id}`}>
                  View transaction detail
                </Link>

                <Link className="text-link" href="/history">
                  View transaction history
                </Link>
              </div>
            </>
          ) : (
            <div className="receipt-actions">
              <Link href="/send?new=1">
                <button type="button">Start another transfer</button>
              </Link>
              <Link className="text-link" href="/history">
                View transaction history
              </Link>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
