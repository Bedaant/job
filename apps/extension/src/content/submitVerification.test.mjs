import { test } from "node:test";
import assert from "node:assert/strict";

import {
  SETTLE_MS,
  VERIFY_TIMEOUT_MS,
  decideVerification,
  isCaptchaChallengeSrc,
  verificationReport,
} from "./submitVerification.mjs";

const FORM_URL = "https://jobs.lever.co/acme/123e4567/apply";
const base = {
  urlBefore: FORM_URL,
  urlAfter: FORM_URL,
  pageText: "Apply for Backend Engineer. Name Email Resume Submit application",
  formStillPresent: true,
  visibleErrorTexts: [],
  captchaVisible: false,
  elapsedMs: 3000,
};
const obs = (o) => ({ ...base, ...o });

test("Lever: navigating to /thanks with 'Application submitted!' is confirmed", () => {
  // Verified against a live jobs.lever.co/<company>/<id>/thanks page.
  const r = decideVerification(obs({
    urlAfter: "https://jobs.lever.co/acme/123e4567/thanks",
    pageText: "SDE I Bangalore Application submitted! Return to the main page",
    formStillPresent: false,
  }));
  assert.equal(r.verdict, "confirmed");
});

test("Greenhouse: navigating to .../confirmation is confirmed even before its text renders", () => {
  const r = decideVerification(obs({
    urlBefore: "https://job-boards.greenhouse.io/acme/jobs/42",
    urlAfter: "https://job-boards.greenhouse.io/acme/jobs/42/confirmation",
    pageText: "",
    formStillPresent: false,
  }));
  assert.equal(r.verdict, "confirmed");
});

test("Ashby: its verified in-page text confirms once the form is gone", () => {
  // From Ashby's page source (docs/LIVE-FORM-TEST.md, 2026-09-27).
  const r = decideVerification(obs({
    urlBefore: "https://jobs.ashbyhq.com/acme/7458d4e9/application",
    urlAfter: "https://jobs.ashbyhq.com/acme/7458d4e9/application",
    pageText: "Your application was successfully submitted. We'll contact you if there are next steps.",
    formStillPresent: false,
  }));
  assert.equal(r.verdict, "confirmed");
});

test("same-page (SPA) confirmation: the form is replaced by thank-you text", () => {
  for (const text of [
    "Thank you for applying to Acme!",
    "Thanks for applying",
    "Your application has been successfully submitted.",
    "Application received",
    "We've received your application and will be in touch.",
    "We have received your application",
    "Thank you for your application",
  ]) {
    const r = decideVerification(obs({ pageText: text, formStillPresent: false }));
    assert.equal(r.verdict, "confirmed", text);
  }
});

test("thank-you text next to a still-present, unchanged form is NOT confirmation", () => {
  // A careers page header can say "Thank you for applying to Acme" above the form itself.
  const r = decideVerification(obs({ pageText: "Thank you for applying to Acme! Name Email", elapsedMs: 1000 }));
  assert.equal(r.verdict, "pending");
});

test("a confirmation-looking URL that did not change is not a signal", () => {
  const url = "https://acme.example/careers/confirmation-engineer/apply";
  const r = decideVerification(obs({ urlBefore: url, urlAfter: url, elapsedMs: 1000 }));
  assert.equal(r.verdict, "pending");
});

test("form still there with errors after settling is rejected, with the error texts", () => {
  const r = decideVerification(obs({ visibleErrorTexts: ["Phone number is invalid"] }));
  assert.equal(r.verdict, "rejected");
  assert.equal(r.code, "validation_errors");
  assert.match(r.reason, /Phone number is invalid/);
});

test("a required-field error is named as such", () => {
  const r = decideVerification(obs({ visibleErrorTexts: ["LinkedIn Profile: This field is required."] }));
  assert.equal(r.verdict, "rejected");
  assert.equal(r.code, "required_field");
});

test("errors are not judged before the page settles (a slow POST may still navigate)", () => {
  const r = decideVerification(obs({ visibleErrorTexts: ["Required"], elapsedMs: SETTLE_MS - 1 }));
  assert.equal(r.verdict, "pending");
});

test("a captcha challenge appearing after submit is rejected as captcha, immediately", () => {
  const r = decideVerification(obs({ captchaVisible: true, elapsedMs: 200 }));
  assert.equal(r.verdict, "rejected");
  assert.equal(r.code, "captcha");
});

test("confirmation beats a stray error element elsewhere on the thank-you page", () => {
  const r = decideVerification(obs({
    urlAfter: "https://jobs.lever.co/acme/123e4567/thanks",
    pageText: "Application submitted!",
    formStillPresent: false,
    visibleErrorTexts: ["Cookie preferences failed to load"],
  }));
  assert.equal(r.verdict, "confirmed");
});

test("no signal before the bound: keep waiting", () => {
  assert.equal(decideVerification(obs({ elapsedMs: VERIFY_TIMEOUT_MS - 1 })).verdict, "pending");
});

test("no signal by the bound: unconfirmed, never confirmed", () => {
  const stayed = decideVerification(obs({ elapsedMs: VERIFY_TIMEOUT_MS }));
  assert.equal(stayed.verdict, "unconfirmed");
  const wentElsewhere = decideVerification(obs({
    urlAfter: "https://acme.example/careers", pageText: "Open roles", formStillPresent: false,
    elapsedMs: VERIFY_TIMEOUT_MS + 5,
  }));
  assert.equal(wentElsewhere.verdict, "unconfirmed");
  assert.ok(wentElsewhere.reason.length > 0);
});

test("wire outcomes: confirmed -> submitted, rejected -> needs_human, unconfirmed -> unconfirmed", () => {
  assert.deepEqual(verificationReport({ verdict: "confirmed", reason: "x" }).outcome, "submitted");
  const rejected = verificationReport({ verdict: "rejected", code: "captcha", reason: "A captcha appeared after submit." });
  assert.equal(rejected.outcome, "needs_human");
  // needs_input.py keys the review card's kind on the word "captcha".
  assert.match(rejected.reason, /captcha/i);
  assert.equal(verificationReport({ verdict: "unconfirmed", reason: "y" }).outcome, "unconfirmed");
  assert.equal(verificationReport({ verdict: "rejected", reason: "z".repeat(5000) }).reason.length, 2000);
});

test("captcha challenge frames are recognised; the invisible badge frame is not", () => {
  assert.ok(isCaptchaChallengeSrc("https://www.google.com/recaptcha/api2/bframe?hl=en"));
  assert.ok(isCaptchaChallengeSrc("https://www.google.com/recaptcha/enterprise/bframe?k=x"));
  assert.ok(isCaptchaChallengeSrc("https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html#frame=challenge"));
  assert.ok(isCaptchaChallengeSrc("https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile"));
  assert.ok(!isCaptchaChallengeSrc("https://www.google.com/recaptcha/api2/anchor?k=x"));
  assert.ok(!isCaptchaChallengeSrc("https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html#frame=checkbox"));
  assert.ok(!isCaptchaChallengeSrc(""));
});
