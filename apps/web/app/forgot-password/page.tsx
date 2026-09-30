"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { Logo } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Reset your password · ApplyScout";
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <Logo className="size-11 text-foreground" />
          <div className="space-y-1.5">
            <h1 className="text-[28px] font-bold tracking-tight">Reset your password</h1>
            <p className="text-muted-foreground">We&apos;ll email you a link to set a new one.</p>
          </div>
        </div>

        {sent ? (
          <p role="status" className="rounded-2xl border bg-card p-6 text-center shadow-sm">
            If an account uses <strong>{email}</strong>, a reset link is on its way. It works once, for an hour.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border bg-card p-6 shadow-sm">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                inputMode="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                aria-invalid={!!error || undefined}
              />
            </div>
            {error && (
              <p role="alert" className="rounded-xl bg-destructive/10 px-3.5 py-2.5 text-sm font-medium text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </Button>
          </form>
        )}

        <p className="text-center text-muted-foreground">
          <Link href="/login" className="inline-flex min-h-11 items-center rounded-lg font-medium text-primary hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
