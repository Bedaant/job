"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BriefcaseIcon, HouseIcon, IdCardIcon, InboxIcon, RocketIcon } from "lucide-react";
import { clearToken, getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/today", label: "Today", Icon: HouseIcon },
  { href: "/review", label: "Review", Icon: InboxIcon },
  { href: "/campaign", label: "Campaign", Icon: RocketIcon },
  { href: "/matches", label: "Matches", Icon: BriefcaseIcon },
  { href: "/facts", label: "Your facts", Icon: IdCardIcon },
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
  pageTitle = title,
  description,
  actions,
  children,
}: {
  title: string;
  /** Document title ("<pageTitle> · ApplyScout") when the heading isn't one, e.g. a greeting. */
  pageTitle?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();

  // Pages are client components, so they can't export `metadata`; set it here.
  useEffect(() => {
    document.title = `${pageTitle} · ApplyScout`;
  }, [pageTitle]);

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
          <Link href="/today" className="flex items-center gap-2.5 rounded-lg font-semibold tracking-tight">
            <Logo />
            <span>ApplyScout</span>
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">
            {NAV.map((item) => {
              const current = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "inline-flex h-10 items-center whitespace-nowrap rounded-full px-4 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
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
            className="ml-auto inline-flex h-10 items-center whitespace-nowrap rounded-full px-4 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Log out
          </button>
        </div>
      </header>
      {/* Below sm the five links don't fit the top bar, so they become a bottom tab bar. */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-xl sm:hidden"
      >
        <ul className="grid grid-cols-5">
          {NAV.map(({ href, label, Icon }) => {
            const current = pathname === href;
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={current ? "page" : undefined}
                  className={cn(
                    "flex min-h-14 flex-col items-center justify-center gap-0.5 px-0.5 py-1.5 text-center text-[11px] font-medium leading-tight text-muted-foreground",
                    current && "font-semibold text-primary"
                  )}
                >
                  <Icon aria-hidden="true" className="size-5" strokeWidth={current ? 2.5 : 2} />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <main
        id="main"
        className="mx-auto max-w-5xl px-4 pb-[calc(6rem+env(safe-area-inset-bottom,0px))] pt-10 sm:px-6 sm:pb-24"
      >
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
