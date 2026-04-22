import type { ReactNode } from "react";
import Link from "next/link";

type TrustSection = {
  title: string;
  body?: string[];
  bullets?: string[];
};

type TrustPageShellProps = {
  eyebrow: string;
  title: string;
  lede: string;
  sections?: TrustSection[];
  children?: ReactNode;
};

const trustLinks = [
  { href: "/terms", label: "Terms of Service" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/refund-policy", label: "Refund Policy" },
  { href: "/compliance", label: "Compliance Disclosures" },
  { href: "/help", label: "Help Center" },
  { href: "/contact", label: "Contact Support" },
];

export function TrustPageShell({
  eyebrow,
  title,
  lede,
  sections = [],
  children,
}: TrustPageShellProps) {
  return (
    <>
      <header className="trust-public-nav">
        <div className="trust-public-nav-inner">
          <Link className="premium-brand" href="/">
            <span className="brand-mark">MP</span>
            <span>
              <span className="brand-name">MbongoPay</span>
              <span className="brand-subtitle">Cross-border money transfers</span>
            </span>
          </Link>

          <nav className="trust-public-links" aria-label="Public navigation">
            <Link href="/">Home</Link>
            <Link href="/help">Help</Link>
            <Link href="/contact">Contact</Link>
          </nav>

          <div className="trust-public-actions">
            <Link className="nav-button ghost" href="/login?mode=login&next=/send">
              Log in
            </Link>
            <Link className="nav-button solid" href="/start">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main className="trust-page">
        <div className="trust-page-shell">
          <header className="trust-page-hero">
            <p className="kicker">{eyebrow}</p>
            <h1>{title}</h1>
            <p className="lede">{lede}</p>
            <p className="trust-page-updated">Last updated April 22, 2026</p>
          </header>

          <div className="trust-page-layout">
            <aside className="trust-page-nav" aria-label="Legal and support pages">
              <p>Trust resources</p>
              <nav>
                {trustLinks.map((link) => (
                  <Link key={link.href} href={link.href}>
                    {link.label}
                  </Link>
                ))}
              </nav>
            </aside>

            <article className="trust-page-content">
              {sections.map((section) => (
                <section className="trust-page-section" key={section.title}>
                  <h2>{section.title}</h2>
                  {section.body?.map((paragraph) => (
                    <p key={paragraph}>{paragraph}</p>
                  ))}
                  {section.bullets ? (
                    <ul>
                      {section.bullets.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : null}
                </section>
              ))}
              {children}
            </article>
          </div>
        </div>
      </main>
    </>
  );
}
