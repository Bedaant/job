"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Logo } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Read after mount (not useSearchParams) so the page stays statically renderable, like /login.
  useEffect(() => {
    document.title = "Set a new password · ApplyScout";
    setToken(new URLSearchParams(window.location.search).get("token"));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setBusy(true);
    try {
      await api.resetPassword(token, password);
      router.push("/login?reset=1");
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
          <h1 className="text-[28px] font-bold tracking-tight">Set a new password</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border bg-card p-6 shadow-sm">
          <div className="space-y-2">
            <Label htmlFor="password">New password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              aria-describedby="password-hint"
              aria-invalid={!!error || undefined}
            />
            <p id="password-hint" className="text-sm text-muted-foreground">At least 8 characters.</p>
          </div>
          {error && (
            <p role="alert" className="rounded-xl bg-destructive/10 px-3.5 py-2.5 text-sm font-medium text-destructive">
              {error}
            </p>
          )}
          <Button type="submit" size="lg" className="w-full" disabled={busy || !token}>
            {busy ? "Saving…" : "Save new password"}
          </Button>
        </form>

        <p className="text-center text-muted-foreground">
          <Link href="/forgot-password" className="inline-flex min-h-11 items-center rounded-lg font-medium text-primary hover:underline">
            Need a new link?
          </Link>
        </p>
      </div>
    </main>
  );
}
