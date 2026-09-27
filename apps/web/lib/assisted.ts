// Assisted apply: Maggie prepares, the user sends. The decisions behind the
// "Ready to send" cards, kept out of components so they test without a DOM.

/** auto_submit=false. The default, and the one we recommend. */
export const ASSISTED = {
  label: "Assisted — Maggie prepares, you send (recommended)",
  description:
    "Maggie finds, ranks and tailors each application. You download the resume, open the form and press Submit yourself.",
};

/** auto_submit=true. */
export const AUTOMATIC = {
  label: "Automatic — Maggie sends within your daily limit",
  description:
    "Maggie submits applications herself from your browser, up to your daily limit, without asking. Anything sent stays sent.",
};

export const submitMode = (autoSubmit: boolean) => (autoSubmit ? AUTOMATIC : ASSISTED);

export function submitModeLine(autoSubmit: boolean): string {
  return autoSubmit
    ? "She sends applications herself, within your daily limit."
    : "She prepares each application; you send it from Review, one tap at a time.";
}

export const EXTENSION_NOTE =
  "Got the ApplyScout extension? On the employer's form, open it and press “Fill this form” — it fills in your details. You still press the employer's Submit.";

/** "Job keywords covered: 50% → 75%", or null when tailoring didn't record it. */
export function coverageChange(gap: Record<string, unknown> | null | undefined): string | null {
  const before = gap?.coverage_before;
  const after = gap?.coverage_after;
  if (typeof before !== "number" || typeof after !== "number") return null;
  return `Job keywords covered: ${Math.round(before * 100)}% → ${Math.round(after * 100)}%`;
}

/** Copy via the Clipboard API; "show" means the caller shows the text to copy by hand. */
export async function copyText(
  text: string,
  clipboard: { writeText: (t: string) => Promise<void> } | undefined,
): Promise<"copied" | "show"> {
  if (!clipboard) return "show"; // insecure context or old browser
  try {
    await clipboard.writeText(text);
    return "copied";
  } catch {
    return "show"; // permission refused
  }
}

export const isHttpUrl = (url: string) => /^https?:\/\//i.test(url);

export function resumeFilename(company: string): string {
  const slug = company.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug ? `resume-${slug}.docx` : "resume.docx";
}

export type SendAction = "sent" | "dismissed";

/** How long "Undo" stays offered before the change is sent to the server. */
export const UNDO_MS = 6000;

export function undoMessage(action: SendAction, job: { title: string; company: string }): string {
  const what = `${job.title} at ${job.company}`;
  return action === "sent" ? `Marked as sent: ${what}.` : `Removed: ${what}.`;
}

/** Review-queue rows that aren't already shown as ready to send. */
export function needsYouOnly<T extends { id: string }>(queue: T[], ready: { id: string }[]): T[] {
  const ids = new Set(ready.map((r) => r.id));
  return queue.filter((a) => !ids.has(a.id));
}
