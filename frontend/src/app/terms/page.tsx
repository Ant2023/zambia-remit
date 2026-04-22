import type { Metadata } from "next";
import { TrustPageShell } from "@/components/TrustPageShell";

export const metadata: Metadata = {
  title: "Terms of Service | MbongoPay",
  description: "Terms for using MbongoPay cross-border transfer services.",
};

const sections = [
  {
    title: "Using MbongoPay",
    body: [
      "These terms apply when you create an account, request a quote, fund a transfer, track a transaction, or use any customer service provided by MbongoPay.",
      "You are responsible for keeping your account details accurate and for using the service only for lawful personal, family, household, or business purposes supported by the product.",
    ],
  },
  {
    title: "Accounts and verification",
    body: [
      "We may ask you to provide identity, contact, recipient, payment, source-of-funds, or transaction-purpose information before we process or release a transfer.",
      "We may delay, reject, cancel, refund, or place a transfer under review when required by risk controls, payment partners, payout partners, or applicable law.",
    ],
  },
  {
    title: "Quotes, fees, and exchange rates",
    body: [
      "Quotes show the send amount, estimated fee, exchange rate, receive amount, and supported payout method available at the time the quote is created.",
      "A quote may expire or become unavailable if rates, limits, partner availability, compliance requirements, or recipient details change before the transfer is submitted.",
    ],
  },
  {
    title: "Payments and payouts",
    body: [
      "A transfer starts processing after we receive or confirm payment and complete required checks. Payout timing depends on funding status, compliance review, provider availability, recipient details, and local banking or mobile money conditions.",
      "You agree that we may rely on the recipient and payout information you provide. Incorrect recipient information may delay the transfer or make recovery difficult after payout.",
    ],
  },
  {
    title: "Restricted use",
    bullets: [
      "Do not use MbongoPay for fraud, deception, unlawful activity, sanctions evasion, or transactions that hide the true sender, recipient, purpose, or source of funds.",
      "Do not attempt to bypass transfer limits, verification requirements, fraud controls, chargeback processes, or compliance reviews.",
      "Do not submit payment information that you are not authorized to use.",
    ],
  },
  {
    title: "Service changes and availability",
    body: [
      "We may change, suspend, or discontinue features, corridors, payout methods, fees, limits, or providers as needed for operations, risk, compliance, or partner requirements.",
      "We may update these terms as the service evolves. Material updates will be reflected on this page.",
    ],
  },
  {
    title: "Questions",
    body: [
      "Contact support if you have questions about these terms, a specific transfer, payment status, payout status, or account access.",
    ],
  },
];

export default function TermsPage() {
  return (
    <TrustPageShell
      eyebrow="Legal"
      title="Terms of Service"
      lede="The rules for using MbongoPay accounts, quotes, payments, transfers, and payout services."
      sections={sections}
    />
  );
}
