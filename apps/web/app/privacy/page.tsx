import Link from "next/link";

// P0 #7 / India DPDP Act 2023: notice before consent. Processors listed from the code
// (apps/api/core/config.py and the modules that call each service). Not legal advice.
const PROCESSORS: [string, string][] = [
  ["Anthropic (Claude) or NVIDIA (NIM)", "AI models that read your resume and facts and the job text to extract facts, tailor resumes and write emails."],
  ["Voyage AI", "Turns your facts and job descriptions into vectors so jobs can be matched to you."],
  ["Langfuse", "Records AI requests and responses so we can find errors and measure quality. These records can contain your facts."],
  ["Apify", "Searches public profiles for people at a company you applied to, when you ask for referral contacts. It receives the company and role, not your resume."],
  ["Google (Gmail)", "Sends referral emails from your own Gmail, only if you connect it. We can send mail; we cannot read your mailbox."],
  ["Our email provider (SMTP)", "Sends your digest and password-reset emails to your address."],
  ["Neon (database) and Redis Cloud (queue)", "Store your account data and run background work."],
];

export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-12 text-sm leading-6">
      <p role="note" className="rounded-xl bg-muted px-4 py-3 font-medium">
        Draft — pending legal review. This notice may change before ApplyScout opens to the public.
      </p>
      <h1 className="text-[28px] font-bold tracking-tight">Privacy notice</h1>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">What we collect</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Your email address and a hash of your password.</li>
          <li>Your resume (read once, then discarded; the file is not stored), and the facts you confirm from it.</li>
          <li>Your contact details: name, phone, address, links and work authorisation, as you enter them.</li>
          <li>Your job preferences, campaigns, matches, applications, answers to application questions and tailored resumes.</li>
          <li>If you use referral outreach: the contacts found and the emails drafted and sent, and your Gmail connection (encrypted).</li>
          <li>When the ApplyScout extension last connected, and what it filled in (field labels and sources, not the values).</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">Why</h2>
        <p>
          Only to find jobs that fit you, prepare applications from facts you confirmed, send what you approve, and tell
          you what happened. We do not sell your data or use it for advertising.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">Who else receives it</h2>
        <ul className="list-disc space-y-1 pl-5">
          {PROCESSORS.map(([name, why]) => (
            <li key={name}>
              <strong>{name}</strong>: {why}
            </li>
          ))}
        </ul>
        <p>Employers receive the applications you send them; recruiters receive the emails you approve.</p>
      </section>

      <section className="space-y-2">
        <h2 className="text-base font-semibold">Your consent and how to delete everything</h2>
        <p>
          You give consent when you create an account, and we record when. You can withdraw it at any time by deleting
          your account: open <strong>Profile</strong>, then <strong>Delete my account</strong>. That removes your
          profile, facts, applications, matches, campaigns, answers, contacts, outreach, notifications and Gmail
          connection from our database straight away, and asks Google to revoke the Gmail grant.
        </p>
        <p>
          Records already held by the services above (for example AI request logs) and applications already sent to
          employers are kept under their own policies; we cannot recall them.
        </p>
      </section>

      <Link href="/login" className="inline-flex min-h-11 items-center font-medium text-primary hover:underline">
        Back
      </Link>
    </main>
  );
}
