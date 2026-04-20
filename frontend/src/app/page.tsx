"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AuthSession } from "@/lib/api";
import { logoutCustomer } from "@/lib/api";
import { clearAuthSession, getStoredAuthSession } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [previewAmount, setPreviewAmount] = useState("100");
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setAuthSession(getStoredAuthSession());
  }, []);

  async function handleLogout() {
    if (authSession?.token) {
      try {
        await logoutCustomer(authSession.token);
      } catch {
        // The local session should still be cleared if the token is already invalid.
      }
    }

    clearAuthSession();
    setAuthSession(null);
    router.push("/login");
  }

  const previewSendAmount = Number(previewAmount) > 0 ? Number(previewAmount) : 0;
  const previewExchangeRate = 25.4;
  const previewFee = 0;
  const previewReceiveAmount = previewSendAmount * previewExchangeRate;
  const previewTotalToPay = previewSendAmount + previewFee;

  function handlePreviewSendMoney() {
    window.sessionStorage.setItem("sendAmount", previewAmount);
    router.push("/send");
  }

  const mapItems = [
    { src: "/flags/us.svg", label: "United States" },
    { src: "/flags/gb.svg", label: "United Kingdom" },
    { src: "/flags/de.svg", label: "Germany" },
    { src: "/flags/zm.svg", label: "Zambia" },
  ];
  const flagRibbonItems = [...mapItems, ...mapItems, ...mapItems];

  return (
    <div className="premium-home">
      <header className="premium-nav">
        <div className="premium-nav-inner">
          <Link className="premium-brand" href="/">
            <span className="brand-mark">FX</span>
            <span>
              <span className="brand-name">Zambia Remit</span>
              <span className="brand-subtitle">Cross-border money transfers</span>
            </span>
          </Link>

          <nav className="premium-links" aria-label="Primary navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#preview">Rates</a>
            <a href="#trust">Security</a>
            <Link href="/history">Help</Link>
          </nav>

          <div className="premium-actions">
            {authSession ? (
              <>
                <span className="signed-in-label">{authSession.user.email}</span>
                <button
                  type="button"
                  className="nav-button ghost"
                  onClick={handleLogout}
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link className="nav-button ghost" href="/login">
                  Log in
                </Link>
                <Link className="nav-button solid" href="/send">
                  Get started
                </Link>
              </>
            )}
          </div>

          <button
            type="button"
            className="mobile-menu-button"
            aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={isMobileMenuOpen}
            onClick={() => setIsMobileMenuOpen((isOpen) => !isOpen)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>

        {isMobileMenuOpen ? (
          <div className="premium-mobile-menu">
            <a href="#how-it-works" onClick={() => setIsMobileMenuOpen(false)}>
              How it works
            </a>
            <a href="#preview" onClick={() => setIsMobileMenuOpen(false)}>
              Rates
            </a>
            <a href="#trust" onClick={() => setIsMobileMenuOpen(false)}>
              Security
            </a>
            <Link href="/history" onClick={() => setIsMobileMenuOpen(false)}>
              Help
            </Link>
            {authSession ? (
              <button type="button" onClick={handleLogout}>
                Log out
              </button>
            ) : (
              <Link href="/login" onClick={() => setIsMobileMenuOpen(false)}>
                Log in
              </Link>
            )}
          </div>
        ) : null}

        <div className="country-flag-ribbon" aria-hidden="true">
          <div className="country-flag-track">
            {flagRibbonItems.map((item, index) => (
              <div className="country-flag-chip" key={`${item.label}-${index}`}>
                <img src={item.src} alt="" />
              </div>
            ))}
          </div>
        </div>
      </header>

      <main>
        <section className="premium-hero">
          <div>
            <div className="premium-pill">
              Secure transfers for modern global payments
            </div>

            <h1>Send money across borders with confidence</h1>
            <p className="lede">
              Fast, transparent, and secure international transfers for families,
              everyday support, and business payments.
            </p>

            <div className="hero-buttons">
              <Link className="hero-button solid" href="/send">
                Start a transfer
              </Link>
              <a className="hero-button ghost" href="#preview">
                View rates
              </a>
            </div>

            <span id="how-it-works" className="hero-anchor" aria-hidden="true" />
          </div>

          <div className="transfer-card preview-card" id="preview">
            <div className="preview-stack rate-check-stack">
              <div className="rate-field">
                <label className="rate-field-label">You send</label>
                <div className="rate-field-control">
                  <input
                    className="rate-amount-input"
                    inputMode="decimal"
                    aria-label="Amount to send"
                    value={previewAmount}
                    onChange={(event) => setPreviewAmount(event.target.value)}
                  />
                  <div className="rate-currency-select">
                    <img
                      className="currency-flag-image"
                      src="/flags/us.svg"
                      alt="United States flag"
                    />
                    <strong>USD</strong>
                    <span aria-hidden="true">v</span>
                  </div>
                </div>
              </div>

              <div className="rate-connector">
                <span className="rate-dot" />
                <div>
                  <span className="rate-badge">First transfer rate</span>
                  <strong>1 USD = {previewExchangeRate.toFixed(2)} ZMW</strong>
                </div>
              </div>

              <div className="rate-field">
                <label className="rate-field-label">They get</label>
                <div className="rate-field-control">
                  <div className="rate-receive-amount">
                    {previewReceiveAmount.toLocaleString("en-US", {
                      maximumFractionDigits: 2,
                    })}
                  </div>
                  <div className="rate-currency-select">
                    <img
                      className="currency-flag-image"
                      src="/flags/zm.svg"
                      alt="Zambia flag"
                    />
                    <strong>ZMW</strong>
                    <span aria-hidden="true">v</span>
                  </div>
                </div>
              </div>

              <div className="receive-method-field">
                <span>Receive method</span>
                <strong>Mobile Money</strong>
                <span aria-hidden="true">v</span>
              </div>

              <dl className="rate-summary-list">
                <div>
                  <dt>Fee</dt>
                  <dd>{previewFee.toFixed(2)} USD</dd>
                </div>
                <div>
                  <dt>Transfer time</dt>
                  <dd>Same day</dd>
                </div>
                <div>
                  <dt>Total to pay</dt>
                  <dd>{previewTotalToPay.toFixed(2)} USD</dd>
                </div>
              </dl>

              <button
                type="button"
                className="preview-continue"
                onClick={handlePreviewSendMoney}
              >
                Send Money
              </button>
            </div>
          </div>
        </section>

        <section className="trust-section" id="trust">
          <div className="trust-panel">
            <div className="trust-grid">
              <div className="trust-card">
                <p>Security</p>
                <h3>Protected every step of the way</h3>
                <span>
                  Built with verification, visibility, and transaction confidence at
                  the core.
                </span>
              </div>

              <div className="trust-card">
                <p>Clarity</p>
                <h3>Know what you send</h3>
                <span>
                  Clear rates, visible fees, and a smoother transfer experience from
                  start to finish.
                </span>
              </div>

              <div className="trust-card">
                <p>Convenience</p>
                <h3>Designed for real life</h3>
                <span>
                  Send for family support, urgent needs, everyday payments, and
                  business use.
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <div className="footer-cta-row">
            <div>
              <Link className="premium-brand footer-brand" href="/">
                <span className="brand-mark">FX</span>
                <span>
                  <span className="brand-name">Zambia Remit</span>
                  <span className="brand-subtitle">
                    Cross-border money transfers
                  </span>
                </span>
              </Link>
              <p className="footer-description">
                Fast, secure, and modern money transfers designed for real life.
              </p>
            </div>

            <div className="footer-cta">
              <p>Ready to send?</p>
              <Link href="/send">Start a transfer</Link>
            </div>
          </div>

          <div className="premium-footer-grid">
            <div>
              <p className="footer-heading">Product</p>
              <div className="footer-links">
                <a href="#how-it-works">How it works</a>
                <a href="#preview">Rates</a>
                <a href="#trust">Security</a>
              </div>
            </div>

            <div>
              <p className="footer-heading">Company</p>
              <div className="footer-links">
                <a href="#trust">About</a>
                <Link href="/history">Support</Link>
                <a href="#trust">Contact</a>
              </div>
            </div>

            <div>
              <p className="footer-heading">Legal</p>
              <div className="footer-links">
                <a href="#trust">Privacy Policy</a>
                <a href="#trust">Terms of Service</a>
                <a href="#trust">Compliance</a>
              </div>
            </div>
          </div>

          <div className="footer-bottom">
            <p>&copy; 2026 Zambia Remit. All rights reserved.</p>
            <p>
              Modern cross-border payments with clarity, security, and confidence.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
