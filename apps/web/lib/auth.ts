const TOKEN_KEY = "job_copilot_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

/** A 401 on login/signup means wrong credentials; anywhere else, the token is dead. */
export function isSessionExpiry(status: number, path: string): boolean {
  return status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/signup");
}

/** Where to go after sign-in: a same-origin path, or null. "//host", "/\host" and
 * tab/newline tricks all resolve off-site in a browser — an open redirect. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || next[0] !== "/" || next[1] === "/" || /[\\\x00-\x20]/.test(next)) return null;
  return next.split(/[?#]/)[0] === "/login" ? null : next;
}

export function expireSession(): void {
  if (typeof window === "undefined") return;
  clearToken();
  const here = window.location.pathname + window.location.search;
  window.location.replace(`/login?expired=1&next=${encodeURIComponent(here)}`);
}
