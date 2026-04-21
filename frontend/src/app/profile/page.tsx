"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type {
  AuthSession,
  Country,
  SenderProfile,
  SenderProfilePayload,
} from "@/lib/api";
import {
  formatApiError,
  getCurrentUser,
  getSenderCountries,
  getSenderProfile,
  requestPasswordReset,
  submitSenderKyc,
  updateCurrentUser,
  updateSenderProfile,
} from "@/lib/api";
import { getStoredAuthSession, saveAuthSession } from "@/lib/auth";

type AccountFormState = {
  email: string;
};

type ProfileFormState = {
  firstName: string;
  lastName: string;
  phoneNumber: string;
  countryId: string;
  dateOfBirth: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  region: string;
  postalCode: string;
};

function getInitialAccountState(session: AuthSession | null): AccountFormState {
  return {
    email: session?.user.email ?? "",
  };
}

function getInitialFormState(profile: SenderProfile | null): ProfileFormState {
  return {
    firstName: profile?.first_name ?? "",
    lastName: profile?.last_name ?? "",
    phoneNumber: profile?.phone_number ?? "",
    countryId: profile?.country?.id ?? "",
    dateOfBirth: profile?.date_of_birth ?? "",
    addressLine1: profile?.address_line_1 ?? "",
    addressLine2: profile?.address_line_2 ?? "",
    city: profile?.city ?? "",
    region: profile?.region ?? "",
    postalCode: profile?.postal_code ?? "",
  };
}

function getCompletionItems(profile: SenderProfile | null) {
  return [
    {
      label: "Legal name",
      complete: Boolean(profile?.first_name && profile.last_name),
    },
    {
      label: "Phone number",
      complete: Boolean(profile?.phone_number),
    },
    {
      label: "Country of residence",
      complete: Boolean(profile?.country),
    },
    {
      label: "Address details",
      complete: Boolean(
        profile?.address_line_1 &&
          profile.city &&
          profile.region &&
          profile.postal_code,
      ),
    },
  ];
}

function formatDate(value?: string) {
  if (!value) {
    return "Not available";
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatKycStatus(value?: string) {
  if (!value) {
    return "Not started";
  }

  return value.replaceAll("_", " ");
}

export default function ProfilePage() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<SenderProfile | null>(null);
  const [senderCountries, setSenderCountries] = useState<Country[]>([]);
  const [accountFormState, setAccountFormState] = useState<AccountFormState>(
    getInitialAccountState(null),
  );
  const [formState, setFormState] = useState<ProfileFormState>(
    getInitialFormState(null),
  );
  const [loading, setLoading] = useState(false);
  const [savingAccount, setSavingAccount] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [sendingReset, setSendingReset] = useState(false);
  const [submittingKyc, setSubmittingKyc] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    const savedSession = getStoredAuthSession();
    setAuthSession(savedSession);
    setAccountFormState(getInitialAccountState(savedSession));

    loadSenderCountryOptions();

    if (savedSession?.token && !savedSession.user.is_staff) {
      loadAccount(savedSession.token, savedSession);
    }
  }, []);

  const completionItems = useMemo(() => getCompletionItems(profile), [profile]);
  const completedItemCount = completionItems.filter((item) => item.complete).length;
  const completionPercent = Math.round(
    (completedItemCount / completionItems.length) * 100,
  );
  const isStaff = Boolean(authSession?.user.is_staff);
  const canSubmitKyc = Boolean(
    profile?.is_complete &&
      profile.kyc_status !== "pending" &&
      profile.kyc_status !== "verified",
  );

  async function loadSenderCountryOptions() {
    try {
      const countries = await getSenderCountries();
      setSenderCountries(countries);
    } catch (apiError) {
      setError(formatApiError(apiError));
    }
  }

  async function loadAccount(
    token = authSession?.token,
    currentSession = authSession,
  ) {
    setError("");
    setSuccessMessage("");

    if (!token) {
      setError("Log in with a customer account first.");
      return;
    }

    setLoading(true);

    try {
      const [user, data] = await Promise.all([
        getCurrentUser(token),
        getSenderProfile(token),
      ]);
      const updatedSession = currentSession
        ? { ...currentSession, user }
        : { token, user };

      setAuthSession(updatedSession);
      saveAuthSession(updatedSession);
      setAccountFormState({ email: user.email });
      setProfile(data);
      setFormState(getInitialFormState(data));
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setLoading(false);
    }
  }

  function updateAccountField<K extends keyof AccountFormState>(
    field: K,
    value: AccountFormState[K],
  ) {
    setAccountFormState((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateProfileField<K extends keyof ProfileFormState>(
    field: K,
    value: ProfileFormState[K],
  ) {
    setFormState((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleAccountSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    const email = accountFormState.email.trim();
    if (!email) {
      setError("Enter the email for this account.");
      return;
    }

    setSavingAccount(true);

    try {
      const user = await updateCurrentUser({ email }, authSession.token);
      const updatedSession = { ...authSession, user };
      setAuthSession(updatedSession);
      saveAuthSession(updatedSession);
      setAccountFormState({ email: user.email });
      setProfile((currentProfile) =>
        currentProfile ? { ...currentProfile, email: user.email } : currentProfile,
      );
      setSuccessMessage("Account email saved.");
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSavingAccount(false);
    }
  }

  async function handlePasswordResetRequest() {
    setError("");
    setSuccessMessage("");

    if (!authSession?.user.email) {
      setError("Log in with a customer account first.");
      return;
    }

    setSendingReset(true);

    try {
      const response = await requestPasswordReset({
        email: authSession.user.email,
      });
      setSuccessMessage(response.detail);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSendingReset(false);
    }
  }

  async function handleKycSubmit() {
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    if (!profile?.is_complete) {
      setError("Complete your sender profile before submitting verification.");
      return;
    }

    setSubmittingKyc(true);

    try {
      const updatedProfile = await submitSenderKyc(authSession.token);
      setProfile(updatedProfile);
      setSuccessMessage("Sender profile submitted for review.");
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSubmittingKyc(false);
    }
  }

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!authSession?.token) {
      setError("Log in with a customer account first.");
      return;
    }

    const payload: SenderProfilePayload = {
      first_name: formState.firstName.trim(),
      last_name: formState.lastName.trim(),
      phone_number: formState.phoneNumber.trim(),
      country_id: formState.countryId,
      date_of_birth: formState.dateOfBirth || null,
      address_line_1: formState.addressLine1.trim(),
      address_line_2: formState.addressLine2.trim(),
      city: formState.city.trim(),
      region: formState.region.trim(),
      postal_code: formState.postalCode.trim(),
    };

    if (!payload.first_name || !payload.last_name) {
      setError("Enter your legal first and last name.");
      return;
    }

    if (!payload.phone_number) {
      setError("Enter your phone number.");
      return;
    }

    if (!payload.country_id) {
      setError("Choose your country of residence.");
      return;
    }

    setSavingProfile(true);

    try {
      const updatedProfile = await updateSenderProfile(payload, authSession.token);
      setProfile(updatedProfile);
      setFormState(getInitialFormState(updatedProfile));
      setSuccessMessage("Profile saved.");

      const updatedSession = {
        ...authSession,
        user: {
          ...authSession.user,
          first_name: updatedProfile.first_name,
          last_name: updatedProfile.last_name,
        },
      };
      setAuthSession(updatedSession);
      saveAuthSession(updatedSession);
    } catch (apiError) {
      setError(formatApiError(apiError));
    } finally {
      setSavingProfile(false);
    }
  }

  return (
    <>
      <AppNavbar />
      <main className="page">
        <div className="shell stack">
          <header className="topbar">
            <div>
              <p className="kicker">Account settings</p>
              <h1>Account and sender profile</h1>
              <p className="lede">
                Manage your login, sender details, and profile readiness without
                leaving the customer account area.
              </p>
            </div>

            <section className="panel stack">
              <h2>Customer account</h2>
              {authSession ? (
                <>
                  <p className="muted small">Signed in as {authSession.user.email}</p>
                  {!isStaff ? (
                    <button type="button" onClick={() => loadAccount()}>
                      {loading ? "Loading..." : "Refresh account"}
                    </button>
                  ) : null}
                </>
              ) : (
                <>
                  <p className="muted small">Log in to manage your account.</p>
                  <Link href="/login?mode=login&next=/profile">
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

          {isStaff ? (
            <section className="panel stack">
              <h2>Staff account</h2>
              <p className="muted">
                Operations accounts manage transfers in the staff console.
              </p>
              <Link href="/operations">
                <button type="button">Open operations</button>
              </Link>
            </section>
          ) : null}

          {!authSession ? (
            <section className="panel stack">
              <h2>Profile access</h2>
              <p className="muted">
                Create or log in to a customer account before saving sender
                details.
              </p>
              <div className="row">
                <Link href="/login?mode=register&next=/profile">
                  <button type="button">Create account</button>
                </Link>
                <Link href="/login?mode=login&next=/profile">
                  <button type="button" className="secondary-button">
                    Log in
                  </button>
                </Link>
              </div>
            </section>
          ) : null}

          {authSession && !isStaff ? (
            <>
              <div className="account-settings-grid">
                <section className="panel stack">
                  <div>
                    <p className="kicker">Account overview</p>
                    <h2>{authSession.user.email}</h2>
                  </div>

                  <dl className="summary-list">
                    <div>
                      <dt>Customer since</dt>
                      <dd>{formatDate(authSession.user.date_joined)}</dd>
                    </div>
                    <div>
                      <dt>Profile status</dt>
                      <dd>{profile?.is_complete ? "Complete" : "Needs details"}</dd>
                    </div>
                    <div>
                      <dt>KYC status</dt>
                      <dd>
                        {profile?.kyc_status_display ??
                          formatKycStatus(profile?.kyc_status)}
                      </dd>
                    </div>
                    <div>
                      <dt>Residence</dt>
                      <dd>{profile?.country?.name ?? "Not set"}</dd>
                    </div>
                  </dl>

                  {profile?.kyc_review_note ? (
                    <p className="notice small">{profile.kyc_review_note}</p>
                  ) : null}

                  {profile?.kyc_status === "pending" ? (
                    <p className="notice small">
                      Verification is pending staff review.
                    </p>
                  ) : null}

                  <div className="row">
                    <Link href="/dashboard">
                      <button type="button" className="secondary-button">
                        Dashboard
                      </button>
                    </Link>
                    <Link href="/history">
                      <button type="button" className="secondary-button">
                        Transaction history
                      </button>
                    </Link>
                    {canSubmitKyc ? (
                      <button
                        type="button"
                        disabled={submittingKyc}
                        onClick={handleKycSubmit}
                      >
                        {submittingKyc
                          ? "Submitting..."
                          : profile?.kyc_status === "rejected" ||
                              profile?.kyc_status === "needs_review"
                            ? "Resubmit verification"
                            : "Submit verification"}
                      </button>
                    ) : null}
                  </div>
                </section>

                <section className="panel stack">
                  <div>
                    <p className="kicker">Login</p>
                    <h2>Email and security</h2>
                  </div>

                  <form className="stack" onSubmit={handleAccountSubmit}>
                    <label>
                      Account email
                      <input
                        type="email"
                        value={accountFormState.email}
                        onChange={(event) =>
                          updateAccountField("email", event.target.value)
                        }
                        autoComplete="email"
                        required
                      />
                    </label>

                    <button type="submit" disabled={savingAccount || loading}>
                      {savingAccount ? "Saving..." : "Save account email"}
                    </button>
                  </form>

                  <div className="profile-section-divider">Security</div>

                  <div className="stack">
                    <p className="muted small">
                      Send yourself a secure reset link. When your password is
                      changed, existing sessions are cleared.
                    </p>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={sendingReset}
                      onClick={handlePasswordResetRequest}
                    >
                      {sendingReset ? "Sending..." : "Send password reset link"}
                    </button>
                  </div>
                </section>
              </div>

              <div className="grid">
                <section className="panel stack">
                  <div>
                    <p className="kicker">Profile progress</p>
                    <h2>
                      {profile?.is_complete
                        ? "Ready to send"
                        : "Finish the essentials"}
                    </h2>
                    <p className="muted small">
                      Required details unlock funding. Address details prepare the
                      account for future verification.
                    </p>
                  </div>

                  <div className="profile-progress">
                    <div>
                      <strong>{completionPercent}%</strong>
                      <span>{completedItemCount} of 4 profile areas complete</span>
                    </div>
                    <progress value={completedItemCount} max={completionItems.length} />
                  </div>

                  <ul className="profile-checklist">
                    {completionItems.map((item) => (
                      <li key={item.label} data-complete={item.complete}>
                        <span>{item.complete ? "Done" : "Needed"}</span>
                        {item.label}
                      </li>
                    ))}
                  </ul>

                  <div className="row">
                    <Link href="/send?new=1">
                      <button type="button">Start a transfer</button>
                    </Link>
                    <Link href="/recipients">
                      <button type="button" className="secondary-button">
                        Manage recipients
                      </button>
                    </Link>
                  </div>
                </section>

                <section className="panel stack">
                  <div>
                    <p className="kicker">Sender details</p>
                    <h2>Profile information</h2>
                  </div>

                  {loading ? <p className="notice">Loading profile...</p> : null}

                  <form className="stack" onSubmit={handleProfileSubmit}>
                    <div className="form-grid">
                      <label>
                        First name
                        <input
                          value={formState.firstName}
                          onChange={(event) =>
                            updateProfileField("firstName", event.target.value)
                          }
                          autoComplete="given-name"
                          required
                        />
                      </label>

                      <label>
                        Last name
                        <input
                          value={formState.lastName}
                          onChange={(event) =>
                            updateProfileField("lastName", event.target.value)
                          }
                          autoComplete="family-name"
                          required
                        />
                      </label>

                      <label>
                        Phone number
                        <input
                          value={formState.phoneNumber}
                          onChange={(event) =>
                            updateProfileField("phoneNumber", event.target.value)
                          }
                          autoComplete="tel"
                          placeholder="+12025550123"
                          required
                        />
                      </label>

                      <label>
                        Country of residence
                        <select
                          value={formState.countryId}
                          onChange={(event) =>
                            updateProfileField("countryId", event.target.value)
                          }
                          required
                        >
                          <option value="" disabled>
                            Select country
                          </option>
                          {senderCountries.map((country) => (
                            <option key={country.id} value={country.id}>
                              {country.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="profile-section-divider">
                      Optional details
                    </div>

                    <div className="form-grid">
                      <label>
                        Date of birth
                        <input
                          type="date"
                          value={formState.dateOfBirth}
                          onChange={(event) =>
                            updateProfileField("dateOfBirth", event.target.value)
                          }
                        />
                      </label>

                      <label>
                        Address line 1
                        <input
                          value={formState.addressLine1}
                          onChange={(event) =>
                            updateProfileField("addressLine1", event.target.value)
                          }
                          autoComplete="address-line1"
                        />
                      </label>

                      <label>
                        Address line 2
                        <input
                          value={formState.addressLine2}
                          onChange={(event) =>
                            updateProfileField("addressLine2", event.target.value)
                          }
                          autoComplete="address-line2"
                        />
                      </label>

                      <label>
                        City
                        <input
                          value={formState.city}
                          onChange={(event) =>
                            updateProfileField("city", event.target.value)
                          }
                          autoComplete="address-level2"
                        />
                      </label>

                      <label>
                        Region
                        <input
                          value={formState.region}
                          onChange={(event) =>
                            updateProfileField("region", event.target.value)
                          }
                          autoComplete="address-level1"
                        />
                      </label>

                      <label>
                        Postal code
                        <input
                          value={formState.postalCode}
                          onChange={(event) =>
                            updateProfileField("postalCode", event.target.value)
                          }
                          autoComplete="postal-code"
                        />
                      </label>
                    </div>

                    <button type="submit" disabled={savingProfile || loading}>
                      {savingProfile ? "Saving..." : "Save profile"}
                    </button>
                  </form>
                </section>
              </div>
            </>
          ) : null}
        </div>
      </main>
    </>
  );
}
