"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppNavbar } from "@/components/AppNavbar";
import type { Transfer } from "@/lib/api";
import { getTransfer } from "@/lib/api";
import { getStoredAuthSession } from "@/lib/auth";

export default function SuccessPage() {
  const [transfer, setTransfer] = useState<Transfer | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const transferId = params.get("transferId");
    const authSession = getStoredAuthSession();
    const savedTransfer = window.sessionStorage.getItem("latestTransfer");

    if (savedTransfer) {
      setTransfer(JSON.parse(savedTransfer) as Transfer);
    }

    if (transferId && authSession?.token) {
      getTransfer(transferId, authSession.token).then((data) => {
        setTransfer(data);
        window.sessionStorage.setItem("latestTransfer", JSON.stringify(data));
      });
    }
  }, []);

  const needsFunding =
    transfer?.status === "awaiting_funding" &&
    transfer?.funding_status !== "received";

  return (
    <>
      <AppNavbar />
      <main className="success-page">
      <section className="success-card stack">
        <p className="kicker">
          {needsFunding ? "Transfer created" : "Transfer funded"}
        </p>
        <h1>{needsFunding ? "Transfer submitted" : "Funding received"}</h1>

        {transfer ? (
          <>
            <p className="lede">
              Reference {transfer.reference} is now {transfer.status_display}.
            </p>

            <dl className="summary-list">
              <div>
                <dt>Send amount</dt>
                <dd>{transfer.send_amount}</dd>
              </div>
              <div>
                <dt>Recipient receives</dt>
                <dd>{transfer.receive_amount}</dd>
              </div>
              <div>
                <dt>Funding</dt>
                <dd>{transfer.funding_status_display}</dd>
              </div>
              <div>
                <dt>Compliance</dt>
                <dd>{transfer.compliance_status_display}</dd>
              </div>
              <div>
                <dt>Payout</dt>
                <dd>{transfer.payout_status_display}</dd>
              </div>
            </dl>

            {needsFunding ? (
              <Link href={`/funding?transferId=${transfer.id}`}>
                <button type="button">Complete funding</button>
              </Link>
            ) : null}
          </>
        ) : (
          <p className="lede">
            The transfer was created, but this browser does not have the latest
            transfer summary saved.
          </p>
        )}

        <Link href="/send?new=1">
          <button type="button">Start another transfer</button>
        </Link>

        <Link className="text-link" href="/history">
          View transaction history
        </Link>
      </section>
      </main>
    </>
  );
}
