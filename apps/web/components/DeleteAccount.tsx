"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import { Button } from "@/components/ui/button";

/** P0 #7: delete the account and every row it owns, behind one confirm step. */
export function DeleteAccount() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount();
      clearToken();
      window.location.replace("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't reach ApplyScout. Nothing was deleted; try again.");
      setBusy(false);
    }
  }

  return (
    <section id="account" aria-labelledby="account-h" className="scroll-mt-24 space-y-4">
      <div className="space-y-1">
        <h2 id="account-h" className="text-2xl font-semibold">Delete my account</h2>
        <p className="text-muted-foreground">
          Removes your profile, facts, applications, matches, campaigns, saved answers, contacts, outreach and Gmail
          connection. It can&apos;t be undone. Applications already sent to employers stay with them. See the{" "}
          <Link href="/privacy" className="font-medium text-primary hover:underline">
            privacy notice
          </Link>
          .
        </p>
      </div>
      {!confirming ? (
        <Button type="button" variant="destructive" className="min-h-11" onClick={() => setConfirming(true)}>
          Delete my account
        </Button>
      ) : (
        <div role="alertdialog" aria-labelledby="account-confirm" className="space-y-3 rounded-xl border p-4">
          <p id="account-confirm" className="font-medium">
            Delete your account and all of its data now?
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="destructive" className="min-h-11" disabled={busy} onClick={remove}>
              {busy ? "Deleting…" : "Yes, delete everything"}
            </Button>
            <Button type="button" variant="outline" className="min-h-11" disabled={busy} onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}
