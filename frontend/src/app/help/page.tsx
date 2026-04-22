import type { Metadata } from "next";
import Link from "next/link";
import { TrustPageShell } from "@/components/TrustPageShell";

export const metadata: Metadata = {
  title: "Help Center | MbongoPay",
  description: "Frequently asked questions for MbongoPay customers.",
};

const faqs = [
  {
    question: "How do I start a transfer?",
    answer:
      "Create or sign in to your customer account, choose the sending and receiving countries, select the recipient, review the quote, and complete the payment step.",
  },
  {
    question: "Why is my transfer awaiting funding?",
    answer:
      "The transfer has been created but payment has not been received or confirmed yet. Open the transfer from your dashboard or history and complete the funding step.",
  },
  {
    question: "Why is my transfer under review?",
    answer:
      "A transfer can enter review because of verification, compliance, fraud, payment, recipient, or payout provider checks. Support can review the transfer reference and explain the next step.",
  },
  {
    question: "When will the recipient receive funds?",
    answer:
      "Timing depends on payment confirmation, compliance status, payout provider availability, payout method, recipient details, and local processing conditions.",
  },
  {
    question: "Can I change recipient details after submitting?",
    answer:
      "Recipient changes may require verification and may not be possible after payout processing starts. If details are wrong, contact support as soon as possible.",
  },
  {
    question: "How do refunds work?",
    answer:
      "Refund availability depends on whether payment was received, whether payout has started or completed, and whether any payment processor or compliance review is required.",
  },
  {
    question: "Where can I find my transfer reference?",
    answer:
      "Transfer references appear in your dashboard, transaction history, transfer detail page, payment confirmation screens, and email notifications.",
  },
];

export default function HelpPage() {
  return (
    <TrustPageShell
      eyebrow="Support"
      title="Help Center"
      lede="Answers to common questions about accounts, transfers, payments, payouts, reviews, and refunds."
    >
      <section className="trust-page-section">
        <h2>Frequently asked questions</h2>
        <div className="faq-list">
          {faqs.map((faq) => (
            <details key={faq.question}>
              <summary>{faq.question}</summary>
              <p>{faq.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="trust-page-section trust-callout">
        <h2>Need account or transfer help?</h2>
        <p>
          Include your transfer reference and account email so support can review
          the right transfer events.
        </p>
        <Link className="text-link" href="/contact">
          Contact support
        </Link>
      </section>
    </TrustPageShell>
  );
}
