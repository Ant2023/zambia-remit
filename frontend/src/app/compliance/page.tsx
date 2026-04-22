import type { Metadata } from "next";
import { TrustPageShell } from "@/components/TrustPageShell";

export const metadata: Metadata = {
  title: "Compliance Disclosures | MbongoPay",
  description: "Customer-facing compliance disclosures for MbongoPay transfers.",
};

const sections = [
  {
    title: "Verification requirements",
    body: [
      "MbongoPay may require sender profile details, recipient payout details, identity review, recipient verification, source-of-funds information, transfer purpose information, or additional documentation before processing a transfer.",
    ],
  },
  {
    title: "Screening and monitoring",
    body: [
      "Transfers may be screened for sanctions, fraud, risk, transaction limits, unusual activity, recipient verification, payment risk, payout provider requirements, and anti-money-laundering monitoring.",
      "Screening can occur when a transfer is created, when payment is authorized or received, before payout, during payout provider updates, and when staff review flags.",
    ],
  },
  {
    title: "Holds and reviews",
    body: [
      "A transfer may be placed on hold or under review when information is incomplete, a rule is triggered, payment requires review, recipient details need verification, or a provider reports an issue.",
      "A review does not always mean a transfer will be rejected. It means the transfer needs additional checks before it can proceed.",
    ],
  },
  {
    title: "Rejected, failed, or refunded transfers",
    body: [
      "MbongoPay may reject, fail, refund, reverse, or cancel a transfer when required by law, partner requirements, unavailable payout routes, fraud controls, incorrect information, or unresolved compliance concerns.",
    ],
  },
  {
    title: "Customer responsibilities",
    bullets: [
      "Provide accurate sender, recipient, payment, and payout information.",
      "Respond to verification or support requests promptly.",
      "Use only payment methods you are authorized to use.",
      "Do not submit transfers connected to prohibited, deceptive, or unlawful activity.",
    ],
  },
  {
    title: "Records and reporting",
    body: [
      "MbongoPay keeps transaction, payment, payout, compliance, notification, and support records to operate the service, investigate issues, meet legal obligations, and support audits or required reporting.",
    ],
  },
];

export default function CompliancePage() {
  return (
    <TrustPageShell
      eyebrow="Trust and safety"
      title="Compliance Disclosures"
      lede="What customers should know about verification, screening, transaction monitoring, holds, and compliance reviews."
      sections={sections}
    />
  );
}
