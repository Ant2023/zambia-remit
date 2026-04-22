import type { Metadata } from "next";
import { TrustPageShell } from "@/components/TrustPageShell";

export const metadata: Metadata = {
  title: "Refund Policy | MbongoPay",
  description: "Refund and cancellation policy for MbongoPay transfers.",
};

const sections = [
  {
    title: "Before payment is received",
    body: [
      "A transfer that has not been funded can usually be cancelled from the customer flow or left unpaid until it expires. No payout will begin until payment is received and required checks are complete.",
    ],
  },
  {
    title: "After payment, before payout",
    body: [
      "If payment has been received but payout has not been completed, support may be able to cancel the transfer and refund the paid amount after compliance, fraud, and payment processor checks.",
      "Refund timing depends on the payment method, card issuer, bank, processor, and any required operational review.",
    ],
  },
  {
    title: "After payout is complete",
    body: [
      "Once funds have been paid out to the recipient or recipient provider, cancellation may not be possible. We will review recovery options where available, but recovery is not guaranteed.",
    ],
  },
  {
    title: "Failed or rejected transactions",
    body: [
      "If MbongoPay cannot complete a transfer because payment fails, compliance rejects the transfer, a payout provider rejects the payout, or recipient information cannot be validated, the transfer may be cancelled, refunded, retried, or held for additional review.",
    ],
  },
  {
    title: "Fees and reversals",
    body: [
      "Where a refund is available, the amount and timing may depend on provider costs, payment status, exchange-rate handling, chargeback activity, and whether a payout attempt already occurred.",
    ],
  },
  {
    title: "How to request help",
    body: [
      "Use the contact page and include your transfer reference, account email, payment method, and a short description of the issue. Support will review the latest payment, payout, and compliance events for the transfer.",
    ],
  },
];

export default function RefundPolicyPage() {
  return (
    <TrustPageShell
      eyebrow="Customer support"
      title="Refund Policy"
      lede="How cancellations, failed transactions, payment reversals, and refund requests are handled."
      sections={sections}
    />
  );
}
