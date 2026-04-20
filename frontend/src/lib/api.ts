export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
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
  is_complete: boolean;
  created_at: string;
  updated_at: string;
};

export type SenderProfilePayload = {
  first_name: string;
  last_name: string;
  phone_number: string;
  country_id: string;
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
  source_country: string;
  destination_country: string;
  source_currency: string;
  destination_currency: string;
  payout_method: "mobile_money" | "bank_deposit";
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

export type MockPaymentMethod = "debit_card" | "bank_transfer";

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
