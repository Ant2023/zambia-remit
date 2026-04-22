import type { Metadata } from "next";
import { TrustPageShell } from "@/components/TrustPageShell";

export const metadata: Metadata = {
  title: "Privacy Policy | MbongoPay",
  description: "How MbongoPay handles customer and transfer information.",
};

const sections = [
  {
    title: "Information we collect",
    bullets: [
      "Account details such as name, email address, phone number, password credentials, and profile information.",
      "Sender, recipient, quote, transfer, payment, payout, compliance, and support details needed to provide the service.",
      "Verification information, review notes, fraud signals, device or request metadata, and operational logs used to secure and monitor transactions.",
    ],
  },
  {
    title: "How we use information",
    body: [
      "We use customer information to create accounts, provide quotes, process transfers, confirm payments, complete payouts, send notifications, support customers, prevent fraud, and meet legal or compliance obligations.",
      "We also use information to maintain records, troubleshoot product issues, improve reliability, and protect customers and the service from unauthorized activity.",
    ],
  },
  {
    title: "How information is shared",
    body: [
      "We may share information with payment processors, payout providers, identity or compliance partners, support providers, professional advisers, and authorities when needed to operate the service or comply with law.",
      "We do not sell customer personal information.",
    ],
  },
  {
    title: "Retention",
    body: [
      "We keep records for as long as needed to provide the service, resolve disputes, support audits, meet legal requirements, prevent fraud, and maintain transaction history.",
    ],
  },
  {
    title: "Security",
    body: [
      "We use access controls, authentication, operational monitoring, and transaction review workflows designed to protect account and transfer information.",
      "No online service can guarantee perfect security, so customers should protect account credentials and contact support if they suspect unauthorized activity.",
    ],
  },
  {
    title: "Customer choices",
    body: [
      "Customers can update profile information in their account. Some transfer, payment, payout, and compliance records may need to be retained even after account information changes.",
    ],
  },
  {
    title: "Contact",
    body: [
      "Contact support for privacy questions, data access requests, correction requests, or account concerns.",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <TrustPageShell
      eyebrow="Privacy"
      title="Privacy Policy"
      lede="How MbongoPay collects, uses, shares, and protects information connected to customer accounts and transfers."
      sections={sections}
    />
  );
}
