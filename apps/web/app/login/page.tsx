"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { safeNext, setToken } from "@/lib/auth";
import { Logo } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expired, setExpired] = useState(false);
  const [wasReset, setWasReset] = useState(false);
  const signup = mode === "signup";

  // Read after mount (not useSearchParams) so the page stays statically renderable.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setExpired(params.has("expired"));
    setWasReset(params.has("reset"));
  }, []);
  useEffect(() => {
    document.title = `${signup ? "Create account" : "Sign in"} · ApplyScout`;
  }, [signup]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (signup) await api.signup(email, password);
      const { access_token } = await api.login(email, password);
      setToken(access_token);
      // A new account has nothing yet — onboarding is where it starts.
      router.push(signup ? "/onboarding" : safeNext(new URLSearchParams(window.location.search).get("next")) ?? "/today");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(signup ? "login" : "signup");
    setError(null); // an error from the other form is not about this one
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <Logo className="size-11 text-foreground" />
          <div className="space-y-1.5">
            <h1 className="text-[28px] font-bold tracking-tight">
              {signup ? "Create your account" : "Welcome back"}
            </h1>
            <p className="text-muted-foreground">
              {signup
                ? "Two minutes to set up. Maggie does the applying."
                : "Sign in to see what Maggie did today."}
            </p>
          </div>
        </div>

        {expired && !signup && (
          <p role="status" className="rounded-xl bg-muted px-4 py-3 text-center text-sm text-muted-foreground">
            Your session ended. Sign in again to pick up where you left off.
          </p>
        )}

        {wasReset && !signup && (
          <p role="status" className="rounded-xl bg-muted px-4 py-3 text-center text-sm text-muted-foreground">
            Your password is changed. Sign in with the new one.
          </p>
        )}

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
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              aria-describedby={signup ? "password-hint" : undefined}
              aria-invalid={!!error || undefined}
            />
            {signup ? (
              <p id="password-hint" className="text-sm text-muted-foreground">
                At least 8 characters.
              </p>
            ) : (
              <Link href="/forgot-password" className="inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline">
                Forgot password?
              </Link>
            )}
          </div>

          {error && (
            <p role="alert" className="rounded-xl bg-destructive/10 px-3.5 py-2.5 text-sm font-medium text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? (signup ? "Creating your account…" : "Signing in…") : signup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="text-center text-muted-foreground">
          {signup ? "Already have an account?" : "New to ApplyScout?"}{" "}
          <button
            type="button"
            onClick={switchMode}
            className="inline-flex min-h-11 items-center rounded-lg font-medium text-primary hover:underline"
          >
            {signup ? "Sign in" : "Create an account"}
          </button>
        </p>
      </div>
    </main>
  );
}
