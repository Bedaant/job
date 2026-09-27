// Type contract for submitVerification.mjs (plain JS so node --test runs it as-is).
export const VERIFY_TIMEOUT_MS: number;
export const SETTLE_MS: number;

export interface VerificationObservation {
  urlBefore: string;
  urlAfter: string;
  pageText: string;
  formStillPresent: boolean;
  visibleErrorTexts: string[];
  captchaVisible: boolean;
  elapsedMs: number;
}

export type Verdict = "confirmed" | "rejected" | "unconfirmed" | "pending";

export interface VerificationResult {
  verdict: Verdict;
  code?: "captcha" | "required_field" | "validation_errors";
  reason: string;
}

export function isCaptchaChallengeSrc(src: string | null | undefined): boolean;
export function decideVerification(obs: VerificationObservation): VerificationResult;
export function verificationReport(result: VerificationResult): {
  outcome: "submitted" | "needs_human" | "unconfirmed";
  reason: string;
};
