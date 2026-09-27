"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clearToken, getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/review", label: "Review" },
  { href: "/matches", label: "Matches" },
  { href: "/facts", label: "Your facts" },
];

/** Redirects to /login when there is no token; true once it is safe to render. */
export function useRequireAuth(): boolean {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);
  return ready;
}

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" aria-hidden="true" className={cn("size-7", className)}>
      <rect width="28" height="28" rx="8" fill="currentColor" />
      <path d="M8 17c2-5 6-8 12-8-2 3-3 6-3 9l-3-2-3 3-1-3z" className="fill-background" />
    </svg>
  );
}

export function AppShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();

  function logOut() {
    clearToken();
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-card focus:px-4 focus:py-2 focus:shadow"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b bg-background/80 pt-[env(safe-area-inset-top,0px)] backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4 sm:px-6">
          <Link href="/review" className="flex items-center gap-2.5 rounded-lg font-semibold tracking-tight">
            <Logo />
            <span className="hidden sm:inline">ApplyScout</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1 overflow-x-auto">
            {NAV.map((item) => {
              const current = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "inline-flex h-10 items-center rounded-full px-4 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                    current && "bg-accent text-accent-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <button
            type="button"
            onClick={logOut}
            className="ml-auto inline-flex h-10 items-center rounded-full px-4 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Log out
          </button>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-5xl px-4 pb-24 pt-10 sm:px-6">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl space-y-2">
            <h1 className="text-3xl font-bold tracking-tight sm:text-[34px]">{title}</h1>
            {description && <p className="text-[17px] leading-relaxed text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
        {children}
      </main>
    </div>
  );
}
