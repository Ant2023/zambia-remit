export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  date_joined: string;
};

export type AuthSession = {
  token: string;
  user: User;
};

export type CustomerLoginPayload = {
  email: string;
  password: string;
};

export type CustomerRegistrationPayload = {
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
};

export type PasswordResetRequestPayload = {
  email: string;
};

export type PasswordResetConfirmPayload = {
  uid: string;
  token: string;
  password: string;
  password_confirm: string;
};

export type UserUpdatePayload = {
  email?: string;
  first_name?: string;
  last_name?: string;
};

export type Currency = {
  id: string;
  code: string;
  name: string;
  minor_unit: number;
};

export type Country = {
  id: string;
  name: string;
  iso_code: string;
  dialing_code: string;
  currency: Currency;
  is_sender_enabled: boolean;
  is_destination_enabled: boolean;
};

export type PayoutProvider = {
  id: string;
  code: string;
  name: string;
  payout_method: "mobile_money" | "bank_deposit";
  is_active: boolean;
};

export type CorridorPayoutProvider = {
  id: string;
  provider: PayoutProvider;
  is_active: boolean;
  priority: number;
  min_send_amount: string | null;
  max_send_amount: string | null;
};

export type CorridorPayoutMethod = {
  id: string;
  payout_method: "mobile_money" | "bank_deposit";
  is_active: boolean;
  min_send_amount: string | null;
  max_send_amount: string | null;
  display_order: number;
  providers: CorridorPayoutProvider[];
};

export type SenderProfile = {
  id: string;
  user: string;
  email: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  country: Country | null;
  date_of_birth: string | null;
  address_line_1: string;
  address_line_2: string;
  city: string;
  region: string;
  postal_code: string;
  kyc_status: string;
  kyc_status_display: string;
  kyc_submitted_at: string | null;
  kyc_reviewed_at: string | null;
  kyc_review_note: string;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
};

export type SenderProfilePayload = {
  first_name: string;
  last_name: string;
  phone_number: string;
  country_id: string;
  date_of_birth?: string | null;
  address_line_1?: string;
  address_line_2?: string;
  city?: string;
  region?: string;
  postal_code?: string;
};

export type Corridor = {
  id: string;
  source_country: Country;
  destination_country: Country;
  source_currency: Currency;
  destination_currency: Currency;
  is_active: boolean;
  min_send_amount: string;
  max_send_amount: string;
  payout_methods: CorridorPayoutMethod[];
};

export type RateEstimate = {
  corridor_id: string;
  source_country: Country;
  destination_country: Country;
  source_currency: Currency;
  destination_currency: Currency;
  exchange_rate: string;
  min_send_amount: string;
  max_send_amount: string;
  send_amount: string | null;
  fee_amount: string | null;
  receive_amount: string | null;
  total_amount: string | null;
};

export type Recipient = {
  id: string;
  first_name: string;
  last_name: string;
  phone_number: string;
  country: Country;
  relationship_to_sender: string;
  verification_status: string;
  verification_status_display: string;
  verification_submitted_at: string | null;
  verification_reviewed_at: string | null;
  verification_review_note: string;
  is_verification_ready: boolean;
  mobile_money_accounts: Array<{
    id: string;
    provider_name: string;
    mobile_number: string;
    account_name: string;
    is_default: boolean;
  }>;
  bank_accounts: Array<{
    id: string;
    bank_name: string;
    account_number: string;
    account_name: string;
    branch_name: string;
    swift_code: string;
    is_default: boolean;
  }>;
  created_at: string;
  updated_at: string;
};

export type Quote = {
  id: string;
  recipient: string | null;
  source_country: Country;
  destination_country: Country;
  source_currency: Currency;
  destination_currency: Currency;
  payout_method: "mobile_money" | "bank_deposit";
  send_amount: string;
  fee_amount: string;
  exchange_rate: string;
  receive_amount: string;
  status: string;
  expires_at: string;
  created_at: string;
  updated_at: string;
};

export type Transfer = {
  id: string;
  reference: string;
  quote: string;
  recipient: string;
  recipient_details: Recipient;
  source_country: string;
  source_country_details: Country;
  destination_country: string;
  destination_country_details: Country;
  source_currency: string;
  source_currency_details: Currency;
  destination_currency: string;
  destination_currency_details: Currency;
  payout_method: "mobile_money" | "bank_deposit";
  payout_provider: string | null;
  payout_provider_details: PayoutProvider | null;
  send_amount: string;
  fee_amount: string;
  exchange_rate: string;
  receive_amount: string;
  status: string;
  status_display: string;
  funding_status: string;
  funding_status_display: string;
  compliance_status: string;
  compliance_status_display: string;
  payout_status: string;
  payout_status_display: string;
  reason_for_transfer: string;
  sender_email: string;
  sender_name: string;
  latest_payment_instruction: PaymentInstruction | null;
  latest_payout_attempt: PayoutAttempt | null;
  status_events: Array<{
    id: string;
    from_status: string;
    from_status_display: string;
    to_status: string;
    to_status_display: string;
    note: string;
    created_at: string;
  }>;
  created_at: string;
  updated_at: string;
};

export type ComplianceFlag = {
  id: string;
  category: string;
  category_display: string;
  severity: string;
  severity_display: string;
  status: string;
  status_display: string;
  code: string;
  title: string;
  description: string;
  metadata: Record<string, unknown>;
  created_by_email: string;
  resolved_by_email: string;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ComplianceEvent = {
  id: string;
  action: string;
  action_display: string;
  from_compliance_status: string;
  from_compliance_status_display: string;
  to_compliance_status: string;
  to_compliance_status_display: string;
  from_transfer_status: string;
  from_transfer_status_display: string;
  to_transfer_status: string;
  to_transfer_status_display: string;
  note: string;
  metadata: Record<string, unknown>;
  performed_by_email: string;
  created_at: string;
  updated_at: string;
};

export type SanctionsCheck = {
  id: string;
  party_type: string;
  party_type_display: string;
  status: string;
  status_display: string;
  screened_name: string;
  provider_name: string;
  provider_reference: string;
  screening_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  match_score: string | null;
  reviewed_by_email: string;
  reviewed_at: string | null;
  review_note: string;
  created_at: string;
  updated_at: string;
};

export type AllowedTransferStatus = {
  status: string;
  label: string;
};

export type OperationalTransfer = Transfer & {
  allowed_next_statuses: AllowedTransferStatus[];
  compliance_flags: ComplianceFlag[];
  compliance_events: ComplianceEvent[];
  sanctions_checks: SanctionsCheck[];
  payment_actions: PaymentAction[];
  payout_attempts: PayoutAttempt[];
  payout_events: PayoutEvent[];
};

export type MockPaymentMethod = "debit_card" | "bank_transfer";

export type PaymentInstructionDetails = {
  title?: string;
  summary?: string;
  steps?: string[];
  test_card?: string;
  processor_code?: string;
  processor_display_name?: string;
  integration_mode?: string;
  next_action?: string;
  session_reference?: string;
  bank_name?: string;
  account_name?: string;
  account_number?: string;
  routing_number?: string;
  amount_label?: string;
  reference?: string;
  card_fields?: Array<{
    name: string;
    label: string;
  }>;
  test_cards?: Array<{
    number: string;
    outcome: string;
    description?: string;
  }>;
  authorization_cardholder_name?: string;
  authorization_masked_card?: string;
  authorization_expiry_month?: number;
  authorization_expiry_year?: number;
  authorization_reference?: string;
  last_authorization_status?: string;
  last_authorization_message?: string;
};

export type PaymentInstruction = {
  id: string;
  transfer: string;
  payment_method: MockPaymentMethod;
  payment_method_display: string;
  provider_name: string;
  provider_reference: string;
  amount: string;
  currency: Currency;
  status: string;
  status_display: string;
  status_reason: string;
  instructions: PaymentInstructionDetails;
  expires_at: string | null;
  authorized_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  reversed_at: string | null;
  refunded_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentAction = {
  id: string;
  transfer: string;
  payment_instruction: string;
  action: string;
  action_display: string;
  status: string;
  status_display: string;
  amount: string;
  currency: Currency;
  provider_name: string;
  provider_reference: string;
  provider_action_reference: string;
  reason_code: string;
  note: string;
  failure_reason: string;
  metadata: Record<string, unknown>;
  requested_by_email: string;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PaymentActionPayload = {
  action: string;
  payment_instruction_id?: string | null;
  amount?: string | null;
  reason_code?: string;
  note: string;
};

export type PayoutAttempt = {
  id: string;
  transfer: string;
  retry_of: string | null;
  provider: PayoutProvider;
  payout_method: "mobile_money" | "bank_deposit";
  provider_reference: string;
  attempt_number: number;
  amount: string;
  currency: Currency;
  status: string;
  status_display: string;
  provider_status: string;
  status_reason: string;
  destination_snapshot: Record<string, unknown>;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  submitted_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  reversed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PayoutEvent = {
  id: string;
  transfer: string;
  payout_attempt: string | null;
  action: string;
  action_display: string;
  from_payout_status: string;
  to_payout_status: string;
  provider_event_id: string;
  note: string;
  metadata: Record<string, unknown>;
  performed_by_email: string;
  created_at: string;
  updated_at: string;
};

export type PayoutSyncPayload = {
  payout_status: string;
  provider_event_id?: string;
  provider_status?: string;
  status_reason?: string;
  metadata?: Record<string, unknown>;
};

export type CardPaymentAuthorizationPayload = {
  cardholder_name: string;
  card_number: string;
  expiry_month: number;
  expiry_year: number;
  cvv: string;
};

export type RecipientPayload = {
  first_name: string;
  last_name: string;
  phone_number: string;
  country_id: string;
  relationship_to_sender: string;
  payout_method: "mobile_money" | "bank_deposit";
  mobile_money_account?: {
    provider_name: string;
    mobile_number: string;
    account_name: string;
  };
  bank_account?: {
    bank_name: string;
    account_number: string;
    account_name: string;
    branch_name?: string;
    swift_code?: string;
  };
};

export type QuotePayload = {
  corridor_id: string;
  recipient_id: string;
  payout_method: "mobile_money" | "bank_deposit";
  send_amount: string;
};

export type TransferPayload = {
  quote_id: string;
  recipient_id: string;
  reason_for_transfer: string;
};

export type MockFundingPayload = {
  payment_method: MockPaymentMethod;
  payment_instruction_id?: string | null;
  note?: string;
};

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

function getAuthorizationHeader(token?: string) {
  return token ? `Token ${token}` : null;
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");

  const authorization = getAuthorizationHeader(token);
  if (authorization) {
    headers.set("Authorization", authorization);
  }

  const response = await fetch(`/api/django${path}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const responseText = await response.text();
  const data =
    responseText && contentType.includes("application/json")
      ? JSON.parse(responseText)
      : responseText;

  if (!response.ok) {
    throw new ApiError("API request failed", response.status, data);
  }

  return data as T;
}

export function registerCustomer(payload: CustomerRegistrationPayload) {
  return apiFetch<AuthSession>("/accounts/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginCustomer(payload: CustomerLoginPayload) {
  return apiFetch<AuthSession>("/accounts/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginStaff(payload: CustomerLoginPayload) {
  return apiFetch<AuthSession>("/accounts/staff-login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function requestPasswordReset(payload: PasswordResetRequestPayload) {
  return apiFetch<{ detail: string }>("/accounts/password-reset", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function confirmPasswordReset(payload: PasswordResetConfirmPayload) {
  return apiFetch<{ detail: string }>("/accounts/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logoutCustomer(token: string) {
  return apiFetch<void>(
    "/accounts/logout",
    {
      method: "POST",
    },
    token,
  );
}

export function getCurrentUser(token: string) {
  return apiFetch<User>("/accounts/me", {}, token);
}

export function updateCurrentUser(payload: UserUpdatePayload, token: string) {
  return apiFetch<User>(
    "/accounts/me",
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getSenderProfile(token: string) {
  return apiFetch<SenderProfile>("/accounts/profile", {}, token);
}

export function updateSenderProfile(payload: SenderProfilePayload, token: string) {
  return apiFetch<SenderProfile>(
    "/accounts/profile",
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function submitSenderKyc(token: string) {
  return apiFetch<SenderProfile>(
    "/accounts/profile/kyc-submit",
    {
      method: "POST",
    },
    token,
  );
}

export function getSenderCountries() {
  return apiFetch<Country[]>("/countries/sender-countries");
}

export function getDestinationCountries() {
  return apiFetch<Country[]>("/countries/destination-countries");
}

export function getCorridors() {
  return apiFetch<Corridor[]>("/countries/corridors");
}

export function getRateEstimate(params: {
  source_country_id: string;
  destination_country_id: string;
  send_amount?: string;
  payout_method?: "mobile_money" | "bank_deposit";
}) {
  const searchParams = new URLSearchParams({
    source_country_id: params.source_country_id,
    destination_country_id: params.destination_country_id,
  });

  if (params.send_amount) {
    searchParams.set("send_amount", params.send_amount);
  }

  if (params.payout_method) {
    searchParams.set("payout_method", params.payout_method);
  }

  return apiFetch<RateEstimate>(`/quotes/rate?${searchParams.toString()}`);
}

export function createRecipient(payload: RecipientPayload, token: string) {
  return apiFetch<Recipient>(
    "/recipients",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getRecipients(token: string) {
  return apiFetch<Recipient[]>("/recipients", {}, token);
}

export function updateRecipient(
  id: string,
  payload: Partial<RecipientPayload>,
  token: string,
) {
  return apiFetch<Recipient>(
    `/recipients/${id}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function submitRecipientVerification(id: string, token: string) {
  return apiFetch<Recipient>(
    `/recipients/${id}/verification-submit`,
    {
      method: "POST",
    },
    token,
  );
}

export function deleteRecipient(id: string, token: string) {
  return apiFetch<void>(
    `/recipients/${id}`,
    {
      method: "DELETE",
    },
    token,
  );
}

export function createQuote(payload: QuotePayload, token: string) {
  return apiFetch<Quote>(
    "/quotes",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function createTransfer(payload: TransferPayload, token: string) {
  return apiFetch<Transfer>(
    "/transfers",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getTransfers(token: string) {
  return apiFetch<Transfer[]>("/transfers", {}, token);
}

export function getTransfer(id: string, token: string) {
  return apiFetch<Transfer>(`/transfers/${id}`, {}, token);
}

export function getOperationalTransfers(
  token: string,
  params: {
    status?: string;
    funding_status?: string;
    compliance_status?: string;
    payout_status?: string;
    q?: string;
  } = {},
) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      searchParams.set(key, value);
    }
  });

  const queryString = searchParams.toString();
  const path = queryString
    ? `/transfers/operations?${queryString}`
    : "/transfers/operations";

  return apiFetch<OperationalTransfer[]>(path, {}, token);
}

export function transitionTransferStatus(
  id: string,
  payload: { status: string; note?: string },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${id}/status`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function applyTransferComplianceAction(
  id: string,
  payload: { action: string; note?: string },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${id}/compliance-actions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function applyTransferPaymentAction(
  id: string,
  payload: PaymentActionPayload,
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${id}/payment-actions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function submitTransferPayout(
  id: string,
  payload: { note?: string },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${id}/payout-attempts`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function syncTransferPayoutAttempt(
  transferId: string,
  attemptId: string,
  payload: PayoutSyncPayload,
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${transferId}/payout-attempts/${attemptId}/sync`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function retryTransferPayoutAttempt(
  transferId: string,
  attemptId: string,
  payload: { note: string },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${transferId}/payout-attempts/${attemptId}/retry`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function reverseTransferPayoutAttempt(
  transferId: string,
  attemptId: string,
  payload: { note: string },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${transferId}/payout-attempts/${attemptId}/reverse`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function reviewTransferSanctionsCheck(
  transferId: string,
  checkId: string,
  payload: {
    status: string;
    review_note?: string;
    provider_reference?: string;
    match_score?: string | null;
  },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${transferId}/sanctions-checks/${checkId}/review`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function reviewTransferAmlFlag(
  transferId: string,
  flagId: string,
  payload: {
    decision: string;
    review_note?: string;
    escalation_destination?: string;
    escalation_reference?: string;
  },
  token: string,
) {
  return apiFetch<OperationalTransfer>(
    `/transfers/${transferId}/aml-flags/${flagId}/review`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function getPaymentInstructions(id: string, token: string) {
  return apiFetch<PaymentInstruction[]>(
    `/transfers/${id}/payment-instructions`,
    {},
    token,
  );
}

export function createPaymentInstruction(
  id: string,
  payload: { payment_method: MockPaymentMethod },
  token: string,
) {
  return apiFetch<PaymentInstruction>(
    `/transfers/${id}/payment-instructions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function authorizeCardPaymentInstruction(
  transferId: string,
  instructionId: string,
  payload: CardPaymentAuthorizationPayload,
  token: string,
) {
  return apiFetch<PaymentInstruction>(
    `/transfers/${transferId}/payment-instructions/${instructionId}/authorize`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function markTransferFunded(
  id: string,
  payload: MockFundingPayload,
  token: string,
) {
  return apiFetch<Transfer>(
    `/transfers/${id}/funding`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token,
  );
}

export function formatApiError(error: unknown) {
  if (error instanceof ApiError) {
    return formatErrorDetails(error.details);
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong.";
}

function formatErrorDetails(details: unknown): string {
  if (!details) {
    return "Something went wrong. Please try again.";
  }

  if (typeof details === "string") {
    return details || "Something went wrong. Please try again.";
  }

  if (Array.isArray(details)) {
    return details.map(formatErrorDetails).join(" ");
  }

  if (typeof details === "object") {
    const record = details as Record<string, unknown>;

    if (typeof record.detail === "string") {
      return record.detail;
    }

    return Object.entries(record)
      .map(([field, value]) => {
        const label =
          field === "non_field_errors"
            ? ""
            : `${field.replaceAll("_", " ")}: `;
        return `${label}${formatErrorDetails(value)}`.trim();
      })
      .filter(Boolean)
      .join(" ");
  }

  return "Something went wrong. Please try again.";
}
