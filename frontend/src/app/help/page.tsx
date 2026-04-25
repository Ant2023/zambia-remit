import type { Metadata } from "next";
import Link from "next/link";
import { AppNavbar } from "@/components/AppNavbar";
import { Card, MobileContainer, PageHeader, StatusBadge } from "@/components/ui";

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
    <>
      <AppNavbar />
      <MobileContainer className="max-w-5xl space-y-5 py-6 sm:py-10">
        <PageHeader
          action={<StatusBadge tone="info">Customer support</StatusBadge>}
          description="Answers to common questions about accounts, transfers, payments, payouts, reviews, and refunds."
          eyebrow="Support"
          title="Help Center"
        />

        <Card className="space-y-4">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-mbongo-navy">
              Frequently asked questions
            </h2>
            <p className="mbp-helper-text">
              Quick answers for the most common transfer questions.
            </p>
          </div>

          <div className="divide-y divide-mbongo-line rounded-lg border border-mbongo-line bg-white">
            {faqs.map((faq) => (
              <details className="group" key={faq.question}>
                <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 text-sm font-bold text-mbongo-navy marker:hidden sm:text-base [&::-webkit-details-marker]:hidden">
                  <span>{faq.question}</span>
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-mbongo-teal-soft text-lg leading-none text-mbongo-navy transition group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="px-4 pb-4 text-sm leading-6 text-mbongo-muted sm:text-base">
                  {faq.answer}
                </p>
              </details>
            ))}
          </div>
        </Card>

        <Card className="space-y-3 bg-mbongo-navy text-white">
          <StatusBadge className="bg-white/10 text-white ring-white/20" tone="info">
            Need help?
          </StatusBadge>
          <h2 className="text-xl font-bold">Need account or transfer help?</h2>
          <p className="text-sm leading-6 text-white/80 sm:text-base">
            Include your transfer reference and account email so support can review
            the right transfer events.
          </p>
          <div className="flex flex-col gap-3 pt-1 sm:flex-row">
            <Link className="mbp-button-accent" href="/contact">
              Contact support
            </Link>
            <Link className="mbp-button-secondary border-white/20 bg-white/10 text-white hover:bg-white/15" href="/">
              Back home
            </Link>
          </div>
        </Card>
      </MobileContainer>
    </>
  );
}
