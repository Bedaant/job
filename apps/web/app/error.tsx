"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

// Route-level error boundary. Never shows the raw error text: it is written for
// developers and can carry internals. The digest goes to the console for support.
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = "Something went wrong · ApplyScout";
    heading.current?.focus();
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center bg-background px-4 py-16 text-foreground">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">ApplyScout</p>
      <h1 ref={heading} tabIndex={-1} className="mt-2 text-2xl font-semibold outline-none">
        Something went wrong on this page
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        It&apos;s on our side, not yours. Try again — if it keeps happening, head back to Today. Nothing you already
        saved was lost.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={reset}
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Try again
        </button>
        <Link
          href="/today"
          className="inline-flex min-h-11 items-center rounded-md border border-input px-4 text-sm font-medium hover:bg-accent"
        >
          Go to Today
        </Link>
      </div>
    </main>
  );
}
