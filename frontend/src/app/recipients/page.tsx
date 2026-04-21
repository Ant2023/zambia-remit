"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { AuthSession, Country, Recipient, RecipientPayload } from "@/lib/api";
import {
  deleteRecipient,
  formatApiError,
  getDestinationCountries,
  getRecipients,
  submitRecipientVerification,
  updateRecipient,
} from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";
import type { PayoutMethod } from "@/lib/transfer-options";

type RecipientFormState = {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  countryId: string;
  relationshipToSender: string;
  payoutMethod: PayoutMethod;
  providerName: string;
  mobileNumber: string;
  mobileAccountName: string;
  bankName: string;
  accountNumber: string;
  bankAccountName: string;
  branchName: string;
  swiftCode: string;
};

function getRecipientName(recipient: Recipient) {
  return `${recipient.first_name} ${recipient.last_name}`.trim();
}

function getDefaultMobileAccount(recipient: Recipient) {
  return (
    recipient.mobile_money_accounts.find((account) => account.is_default) ??
    recipient.mobile_money_accounts[0]
  );
}

function getDefaultBankAccount(recipient: Recipient) {
  return (
    recipient.bank_accounts.find((account) => account.is_default) ??
    recipient.bank_accounts[0]
  );
}

function getInitialFormState(
  recipient: Recipient | null,
  destinationCountries: Country[],
): RecipientFormState {
  const mobileAccount = recipient ? getDefaultMobileAccount(recipient) : undefined;
  const bankAccount = recipient ? getDefaultBankAccount(recipient) : undefined;
  const payoutMethod: PayoutMethod =
    mobileAccount || !bankAccount ? "mobile_money" : "bank_deposit";

  return {
    firstName: recipient?.first_name ?? "",
    lastName: recipient?.last_name ?? "",
    phoneNumber: recipient?.phone_number ?? "",
    countryId: recipient?.country.id ?? destinationCountries[0]?.id ?? "",
    relationshipToSender: recipient?.relationship_to_sender ?? "",
    payoutMethod,
    providerName: mobileAccount?.provider_name ?? "MTN",
    mobileNumber: mobileAccount?.mobile_number ?? "",
    mobileAccountName: mobileAccount?.account_name ?? "",
    bankName: bankAccount?.bank_name ?? "",
    accountNumber: bankAccount?.account_number ?? "",
    bankAccountName: bankAccount?.account_name ?? "",
    branchName: bankAccount?.branch_name ?? "",
    swiftCode: bankAccount?.swift_code ?? "",
  };
}

function getPayoutSummary(recipient: Recipient) {
  const mobileAccount = getDefaultMobileAccount(recipient);
  const bankAccount = getDefaultBankAccount(recipient);

  if (mobileAccount && bankAccount) {
    return `${mobileAccount.provider_name} and ${bankAccount.bank_name}`;
  }

  if (mobileAccount) {
    return `${mobileAccount.provider_name} mobile money`;
  }

  if (bankAccount) {
    return `${bankAccount.bank_name} bank`;
  }

  return "No payout account";
}

function getVerificationLabel(recipient: Recipient) {
  return recipient.verification_status_display || recipient.verification_status;
}

export default function RecipientsPage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [destinationCountries, setDestinationCountries] = useState<Country[]>([]);
  const [selectedRecipientId, setSelectedRecipientId] = useState("");
  const [formState, setFormState] = useState<RecipientFormState>(
    getInitialFormState(null, []),
  );
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [submittingVerification, setSubmittingVerification] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const selectedRecipient = useMemo(
    () =>
      recipients.find((recipient) => recipient.id === selectedRecipientId) ??
      null,
    [recipients, selectedRecipientId],
  );

  useEffect(() => {
    const savedSession = getStoredAuthSession();
    setAuthSession(savedSession);

    loadDestinationCountries();

    if (savedSession) {
      loadRecipients(savedSession.token);
    }
  }, []);

  useEffect(() => {
    if (!selectedRecipientId && recipients[0]) {
      setSelectedRecipientId(recipients[0].id);
    }
  }, [recipients, selectedRecipientId]);

  useEffect(() => {
    setFormState(getInitialFormState(selectedRecipient, destinationCountries));
  }, [destinationCountries, selectedRecipient]);

  async function loadDestinationCountries() {
    try {
      const countries = await getDestinationCountries();
      setDestinationCountries(countries);
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  async function loadRecipients(token = authSession?.token) {
    setError("");

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    setLoading(true);

    try {
      const data = await getRecipients(token);
      setRecipients(data);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  function updateField<K extends keyof RecipientFormState>(
    field: K,
    value: RecipientFormState[K],
  ) {
    setFormState((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!selectedRecipient) {
      setError("Choose a recipient to update.");
      return;
    }

    const payload: Partial<RecipientPayload> = {
      first_name: formState.firstName.trim(),
      last_name: formState.lastName.trim(),
      phone_number: formState.phoneNumber.trim(),
      country_id: formState.countryId,
      relationship_to_sender: formState.relationshipToSender.trim(),
    };

    if (!payload.first_name || !payload.last_name || !payload.country_id) {
      setError("Enter the recipient name and destination country.");
      return;
    }

    if (formState.payoutMethod === "mobile_money") {
      if (!formState.providerName || !formState.mobileNumber) {
        setError("Enter the mobile money provider and number.");
        return;
      }

      payload.mobile_money_account = {
        provider_name: formState.providerName.trim(),
        mobile_number: formState.mobileNumber.trim(),
        account_name: formState.mobileAccountName.trim(),
      };
    }

    if (formState.payoutMethod === "bank_deposit") {
      if (!formState.bankName || !formState.accountNumber) {
        setError("Enter the bank name and account number.");
        return;
      }

      payload.bank_account = {
        bank_name: formState.bankName.trim(),
        account_number: formState.accountNumber.trim(),
        account_name: formState.bankAccountName.trim(),
        branch_name: formState.branchName.trim(),
        swift_code: formState.swiftCode.trim(),
      };
    }

    setSaving(true);

    try {
      const updatedRecipient = await updateRecipient(
        selectedRecipient.id,
        payload,
        authSession.token,
      );
      setRecipients((current) =>
        current.map((recipient) =>
          recipient.id === updatedRecipient.id ? updatedRecipient : recipient,
        ),
      );
      setSelectedRecipientId(updatedRecipient.id);
      setSuccessMessage("Recipient updated.");
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!selectedRecipient) {
      setError("Choose a recipient to delete.");
      return;
    }

    const confirmed = window.confirm(
      `Delete ${getRecipientName(selectedRecipient)} from saved recipients?`,
    );

    if (!confirmed) {
      return;
    }

    setDeleting(true);

    try {
      await deleteRecipient(selectedRecipient.id, authSession.token);
      setRecipients((current) =>
        current.filter((recipient) => recipient.id !== selectedRecipient.id),
      );
      setSelectedRecipientId("");
      setSuccessMessage("Recipient deleted.");
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setDeleting(false);
    }
  }

  async function handleVerificationSubmit() {
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!selectedRecipient) {
      setError("Choose a recipient first.");
      return;
    }

    setSubmittingVerification(true);

    try {
      const updatedRecipient = await submitRecipientVerification(
        selectedRecipient.id,
        authSession.token,
      );
      setRecipients((current) =>
        current.map((recipient) =>
          recipient.id === updatedRecipient.id ? updatedRecipient : recipient,
        ),
      );
      setSuccessMessage("Recipient submitted for verification.");
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSubmittingVerification(false);
    }
  }

  return (
    <>
      <AppNavbar />
      <main className="page">
        <div className="shell stack">
          <header className="topbar">
            <div>
              <p className="kicker">Recipients</p>
              <h1>Saved recipients</h1>
              <p className="lede">
                Manage people and payout details before starting a transfer.
              </p>
              <Link className="text-link" href="/send?new=1">
                Start a new transfer
              </Link>
            </div>

            <section className="panel stack">
              <h2>Customer account</h2>
              {authSession ? (
                <>
                  <p className="muted small">Signed in as {authSession.user.email}</p>
                  <button type="button" onClick={() => loadRecipients()}>
                    {loading ? "Loading..." : "Refresh recipients"}
                  </button>
                </>
              ) : (
                <>
                  <p className="muted small">Log in to manage recipients.</p>
                  <Link href="/login?mode=login&next=/recipients">
                    <button type="button">Log in</button>
                  </Link>
                </>
              )}
            </section>
          </header>

          {error ? <pre className="error small">{error}</pre> : null}
          {successMessage ? (
            <p className="success small">{successMessage}</p>
          ) : null}

          <div className="recipient-management-grid">
            <section className="panel stack">
              <h2>Recipient list</h2>

              {loading ? <p className="notice">Loading recipients...</p> : null}

              {!loading && recipients.length === 0 ? (
                <div className="stack">
                  <p className="muted">No saved recipients yet.</p>
                  <Link href="/send?new=1">
                    <button type="button">Add recipient in send flow</button>
                  </Link>
                </div>
              ) : null}

              {recipients.length > 0 ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Country</th>
                        <th>Payout</th>
                        <th>Verification</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.map((recipient) => (
                        <tr key={recipient.id}>
                          <td>{getRecipientName(recipient)}</td>
                          <td>{recipient.country.name}</td>
                          <td>{getPayoutSummary(recipient)}</td>
                          <td>{getVerificationLabel(recipient)}</td>
                          <td>
                            <button
                              type="button"
                              className="table-action-button"
                              onClick={() => setSelectedRecipientId(recipient.id)}
                            >
                              Edit
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </section>

            <section className="panel stack">
              <h2>Recipient details</h2>

              {selectedRecipient ? (
                <>
                  <dl className="summary-list">
                    <div>
                      <dt>Verification</dt>
                      <dd>{getVerificationLabel(selectedRecipient)}</dd>
                    </div>
                    <div>
                      <dt>Ready to submit</dt>
                      <dd>{selectedRecipient.is_verification_ready ? "Yes" : "Needs payout details"}</dd>
                    </div>
                  </dl>

                  {selectedRecipient.verification_review_note ? (
                    <p className="notice small">
                      {selectedRecipient.verification_review_note}
                    </p>
                  ) : null}

                  <div className="row">
                    {selectedRecipient.is_verification_ready &&
                    selectedRecipient.verification_status !== "pending" &&
                    selectedRecipient.verification_status !== "verified" ? (
                      <button
                        type="button"
                        disabled={submittingVerification || !authSession}
                        onClick={handleVerificationSubmit}
                      >
                        {submittingVerification
                          ? "Submitting..."
                          : selectedRecipient.verification_status === "rejected" ||
                              selectedRecipient.verification_status === "needs_review"
                            ? "Resubmit verification"
                            : "Submit verification"}
                      </button>
                    ) : null}
                  </div>

                  <form className="stack" onSubmit={handleSubmit}>
                    <div className="form-grid">
                      <label>
                        First name
                        <input
                          value={formState.firstName}
                          onChange={(event) =>
                            updateField("firstName", event.target.value)
                          }
                          required
                        />
                      </label>

                      <label>
                        Last name
                        <input
                          value={formState.lastName}
                          onChange={(event) =>
                            updateField("lastName", event.target.value)
                          }
                          required
                        />
                      </label>

                      <label>
                        Phone number
                        <input
                          value={formState.phoneNumber}
                          onChange={(event) =>
                            updateField("phoneNumber", event.target.value)
                          }
                        />
                      </label>

                      <label>
                        Relationship
                        <input
                          value={formState.relationshipToSender}
                          onChange={(event) =>
                            updateField("relationshipToSender", event.target.value)
                          }
                        />
                      </label>

                      <label>
                        Destination country
                        <select
                          value={formState.countryId}
                          onChange={(event) =>
                            updateField("countryId", event.target.value)
                          }
                          required
                        >
                          <option value="" disabled>
                            Select country
                          </option>
                          {destinationCountries.map((country) => (
                            <option key={country.id} value={country.id}>
                              {country.name}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label>
                        Payout method
                        <select
                          value={formState.payoutMethod}
                          onChange={(event) =>
                            updateField(
                              "payoutMethod",
                              event.target.value as PayoutMethod,
                            )
                          }
                        >
                          <option value="mobile_money">Mobile money</option>
                          <option value="bank_deposit">Bank deposit</option>
                        </select>
                      </label>
                    </div>

                    {formState.payoutMethod === "mobile_money" ? (
                      <div className="form-grid">
                        <label>
                          Provider
                          <select
                            value={formState.providerName}
                            onChange={(event) =>
                              updateField("providerName", event.target.value)
                            }
                          >
                            <option value="MTN">MTN</option>
                            <option value="Airtel">Airtel</option>
                          </select>
                        </label>

                        <label>
                          Mobile money number
                          <input
                            value={formState.mobileNumber}
                            onChange={(event) =>
                              updateField("mobileNumber", event.target.value)
                            }
                            required
                          />
                        </label>

                        <label className="full">
                          Account name
                          <input
                            value={formState.mobileAccountName}
                            onChange={(event) =>
                              updateField("mobileAccountName", event.target.value)
                            }
                          />
                        </label>
                      </div>
                    ) : (
                      <div className="form-grid">
                        <label>
                          Bank name
                          <input
                            value={formState.bankName}
                            onChange={(event) =>
                              updateField("bankName", event.target.value)
                            }
                            required
                          />
                        </label>

                        <label>
                          Account number
                          <input
                            value={formState.accountNumber}
                            onChange={(event) =>
                              updateField("accountNumber", event.target.value)
                            }
                            required
                          />
                        </label>

                        <label>
                          Account name
                          <input
                            value={formState.bankAccountName}
                            onChange={(event) =>
                              updateField("bankAccountName", event.target.value)
                            }
                          />
                        </label>

                        <label>
                          Branch
                          <input
                            value={formState.branchName}
                            onChange={(event) =>
                              updateField("branchName", event.target.value)
                            }
                          />
                        </label>

                        <label className="full">
                          SWIFT code
                          <input
                            value={formState.swiftCode}
                            onChange={(event) =>
                              updateField("swiftCode", event.target.value)
                            }
                          />
                        </label>
                      </div>
                    )}

                    <div className="row">
                      <button type="submit" disabled={saving || !authSession}>
                        {saving ? "Saving..." : "Save changes"}
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        disabled={deleting || !authSession}
                        onClick={handleDelete}
                      >
                        {deleting ? "Deleting..." : "Delete recipient"}
                      </button>
                    </div>
                  </form>
                </>
              ) : (
                <p className="muted">Choose a recipient to view or edit details.</p>
              )}
            </section>
          </div>
        </div>
      </main>
    </>
  );
}
