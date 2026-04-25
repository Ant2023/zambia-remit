import type { Transfer } from "@/lib/api";
import { cn } from "@/lib/cn";
import { StatusBadge } from "./ui";

type CustomerStatus = "initiated" | "in_progress" | "completed" | "failed";
type CustomerStep = Exclude<CustomerStatus, "failed">;
type StepState = "complete" | "active" | "pending";

const CUSTOMER_STATUS_STEPS: Array<{
  key: CustomerStep;
  label: string;
}> = [
  { key: "initiated", label: "Transfer initiated" },
  { key: "in_progress", label: "In progress" },
  { key: "completed", label: "Completed" },
];

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="3"
      viewBox="0 0 24 24"
    >
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function DotIcon() {
  return <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-current" />;
}

export function getCustomerStatus(transfer: Transfer): CustomerStatus {
  if (transfer.status === "failed") {
    return "failed";
  }

  if (transfer.status === "paid_out" || transfer.status === "completed") {
    return "completed";
  }

  if (transfer.status === "approved" || transfer.status === "processing_payout") {
    return "in_progress";
  }

  return "initiated";
}

export function getCustomerStatusLabel(transfer: Transfer) {
  const status = getCustomerStatus(transfer);

  if (status === "failed") {
    return "Failed";
  }

  return (
    CUSTOMER_STATUS_STEPS.find((step) => step.key === status)?.label ??
    "Transfer initiated"
  );
}

function getStepState(transfer: Transfer, step: CustomerStep): StepState {
  const status = getCustomerStatus(transfer);
  const currentIndex = CUSTOMER_STATUS_STEPS.findIndex((item) => item.key === status);
  const stepIndex = CUSTOMER_STATUS_STEPS.findIndex((item) => item.key === step);

  if (status === "failed") {
    return step === "initiated" ? "complete" : "pending";
  }

  if (stepIndex < currentIndex) {
    return "complete";
  }

  if (stepIndex === currentIndex) {
    return status === "completed" ? "complete" : "active";
  }

  return "pending";
}

function getStepDetail(transfer: Transfer, step: CustomerStep, state: StepState) {
  if (state === "pending") {
    return "Pending";
  }

  if (step === "initiated") {
    return formatStatusDate(transfer.created_at);
  }

  if (state === "active" || step === "completed") {
    return formatStatusDate(transfer.updated_at);
  }

  return "Done";
}

function formatStatusDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function TransferStatusStepper({ transfer }: { transfer: Transfer }) {
  const customerStatus = getCustomerStatus(transfer);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="mbp-helper-text">
          {customerStatus === "failed"
            ? "This transfer could not be completed."
            : "Track the transfer from submission to delivery."}
        </p>
        {customerStatus === "failed" ? (
          <StatusBadge tone="error">Failed</StatusBadge>
        ) : null}
      </div>

      <ol className="grid gap-0 rounded-mbongo border border-mbongo-line bg-white p-4">
        {CUSTOMER_STATUS_STEPS.map((step, index) => {
          const state = getStepState(transfer, step.key);
          const isLast = index === CUSTOMER_STATUS_STEPS.length - 1;

          return (
            <li
              className={cn(
                "relative grid grid-cols-[2.75rem_minmax(0,1fr)] gap-3 pb-5 last:pb-0",
                state === "active" && "rounded-lg bg-mbongo-teal-soft/70 py-3 pr-3",
              )}
              key={step.key}
            >
              <div className="relative flex justify-center">
                <span
                  className={cn(
                    "z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border-2 text-sm transition",
                    state === "complete" &&
                      "border-mbongo-teal bg-mbongo-teal text-white shadow-sm",
                    state === "active" &&
                      "border-mbongo-teal bg-white text-mbongo-teal ring-4 ring-mbongo-teal/20",
                    state === "pending" &&
                      "border-mbongo-line bg-slate-50 text-mbongo-muted",
                  )}
                >
                  {state === "complete" ? <CheckIcon /> : <DotIcon />}
                </span>
                {!isLast ? (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "absolute left-1/2 top-9 h-[calc(100%+1.25rem)] w-0.5 -translate-x-1/2",
                      state === "complete" ? "bg-mbongo-teal" : "bg-mbongo-line",
                    )}
                  />
                ) : null}
              </div>

              <div className="min-w-0 pt-1">
                <div className="flex flex-wrap items-center gap-2">
                  <strong
                    className={cn(
                      "text-sm font-bold leading-5 sm:text-base",
                      state === "pending" ? "text-mbongo-muted" : "text-mbongo-navy",
                    )}
                  >
                    {step.label}
                  </strong>
                  {state === "active" ? (
                    <StatusBadge className="normal-case tracking-normal" tone="success">
                      Current
                    </StatusBadge>
                  ) : null}
                </div>
                <p
                  className={cn(
                    "mt-1 text-sm leading-5",
                    state === "pending" ? "text-mbongo-muted" : "text-mbongo-text",
                  )}
                >
                  {getStepDetail(transfer, step.key, state)}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
