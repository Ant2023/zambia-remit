import type { FxRateSnapshot } from "@/lib/api";

const OPEN_EXCHANGE_RATES_SOURCE = "open_exchange_rates";

function toTitleCase(value: string) {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatFxProviderName(value?: string | null) {
  if (!value) {
    return "Pricing engine";
  }

  if (value === OPEN_EXCHANGE_RATES_SOURCE) {
    return "Open Exchange Rates";
  }

  return toTitleCase(value.replaceAll("_", " "));
}

export function getFxRateBadgeText(snapshot?: FxRateSnapshot | null) {
  if (!snapshot) {
    return "Exchange rate";
  }

  if (snapshot.is_primary_rate && snapshot.rate_source === OPEN_EXCHANGE_RATES_SOURCE) {
    return "Live Open Exchange rate";
  }

  if (snapshot.is_primary_rate && snapshot.is_live_rate) {
    return "Live market rate";
  }

  if (snapshot.is_live_rate) {
    return "Fallback live rate";
  }

  return "Reference rate";
}

export function getFxRateSourceSummary(snapshot?: FxRateSnapshot | null) {
  if (!snapshot) {
    return "Pending";
  }

  const providerName = formatFxProviderName(
    snapshot.rate_provider_name || snapshot.rate_source,
  );

  if (snapshot.is_primary_rate && snapshot.is_live_rate) {
    return `${providerName} live rate`;
  }

  if (snapshot.is_live_rate) {
    return `${providerName} live fallback`;
  }

  return `${providerName} reference rate`;
}

export function getFxRateSourceDescription(snapshot?: FxRateSnapshot | null) {
  if (!snapshot) {
    return "Select countries and an amount to load the current exchange rate.";
  }

  const providerName = formatFxProviderName(
    snapshot.rate_provider_name || snapshot.rate_source,
  );

  if (snapshot.is_primary_rate && snapshot.is_live_rate) {
    return `This rate is coming live from ${providerName}.`;
  }

  if (snapshot.is_live_rate) {
    return `${providerName} is being used as a live fallback for this rate.`;
  }

  return `${providerName} is being used as the latest stored reference rate.`;
}
