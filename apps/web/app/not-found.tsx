import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center bg-background px-4 py-16 text-foreground">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">ApplyScout</p>
      <h1 className="mt-2 text-2xl font-semibold">We couldn&apos;t find that page</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        The link may be old, or the page may have moved. Nothing about your job search has changed.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href="/today"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Go to Today
        </Link>
        <Link
          href="/login"
          className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
