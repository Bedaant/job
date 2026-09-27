import type { NeedsInput } from "./api";

export const DEMOGRAPHIC_NOTE =
  "This form requires a self-identification question (gender, ethnicity, veteran or disability status). ApplyScout never answers these, so open the form and answer it yourself. Optional ones are left blank automatically.";

export interface NeedsInputView {
  tone: "warning" | "info";
  title: string;
  body: string;
  /** Show "Open the form": the user has to finish this one by hand. */
  openForm: boolean;
  /** Approving again can actually get it sent. False means a retry stops at the same place. */
  retryHelps: boolean;
  demographicNote: string | null;
}

/** Why Maggie stopped on this form, in plain words. Kind comes from the API (needs_input.py). */
export function needsInputView(n: NeedsInput | null, company: string, pendingCount: number): NeedsInputView | null {
  if (!n) return null;
  const form = `${company}'s form`;
  // A demographic field stops every pass (the extension never fills one), so a retry can't help.
  const demographicNote = n.demographic_left_blank ? DEMOGRAPHIC_NOTE : null;
  const byHand = { tone: "warning" as const, openForm: true, retryHelps: false, demographicNote };

  switch (n.kind) {
    case "captcha":
      return { ...byHand, title: `Maggie stopped at a captcha on ${form}.`, body: "Open the form, solve it, and submit it yourself." };
    case "account":
      return {
        ...byHand,
        title: `Maggie needs an account on ${company}'s site to apply.`,
        body: "Open the form, sign in or create an account, and submit it yourself.",
      };
    case "upload":
      return {
        ...byHand,
        title: `${form} asks for a file Maggie doesn't have.`,
        body: "It needs a file other than your resume. Open the form, add it, and submit it yourself.",
      };
    case "question":
      if (demographicNote) {
        return {
          ...byHand,
          title: `Maggie needs your input to finish ${form}.`,
          body: "Answer any questions below so later forms fill themselves, then open this form and submit it yourself.",
        };
      }
      return pendingCount > 0
        ? {
            tone: "info",
            title: `Maggie needs your answer to finish ${form}.`,
            body: "Answer once. It's saved and reused on every later form that asks. Then approve to retry.",
            openForm: false,
            retryHelps: true,
            demographicNote: null,
          }
        : {
            tone: "info",
            title: `You've answered everything ${form} asked.`,
            body: "Approve to retry and Maggie will fill it in.",
            openForm: false,
            retryHelps: true,
            demographicNote: null,
          };
    default:
      return {
        ...byHand,
        title: `Maggie couldn't finish ${form}.`,
        body: demographicNote
          ? "Open the form, answer or decline those questions, and submit it yourself."
          : `She reported: "${n.message}". Open the form to finish it yourself.`,
      };
  }
}
