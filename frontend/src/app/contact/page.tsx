import type { Metadata } from "next";
import { TrustPageShell } from "@/components/TrustPageShell";
import { SupportForm } from "./SupportForm";

export const metadata: Metadata = {
  title: "Contact Support | MbongoPay",
  description: "Contact MbongoPay support for account and transfer help.",
};

export default function ContactPage() {
  return (
    <TrustPageShell
      eyebrow="Support"
      title="Contact Support"
      lede="Send the details support needs to review account access, payment, payout, refund, verification, or transfer status issues."
    >
      <section className="trust-page-section">
        <h2>Support request</h2>
        <p>
          For transfer questions, include the reference from your dashboard,
          history, receipt email, or transfer detail page.
        </p>
        <SupportForm />
      </section>

      <section className="trust-page-section">
        <h2>Before contacting support</h2>
        <ul>
          <li>Check your dashboard for the latest transfer status.</li>
          <li>Review recent payment, receipt, or payout notification emails.</li>
          <li>Confirm recipient payout details before requesting a retry.</li>
          <li>For refund requests, include the reason and payment method.</li>
        </ul>
      </section>
    </TrustPageShell>
  );
}
