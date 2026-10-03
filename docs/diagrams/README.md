# Diagrams

Interactive diagrams of Job Copilot, made with [Archify](https://github.com/tt-a1i/archify) (MIT). Each is one self-contained HTML file. Download it and open it in a browser. Each has a light and dark theme and an Export menu (PNG, SVG and more).

| File | Shows |
|---|---|
| [`job-copilot-architecture.html`](job-copilot-architecture.html) | The system: web app, API, database, queue, workers, AI services, form planner, extension, and the planned outreach parts |
| [`job-copilot-loop.html`](job-copilot-loop.html) | The flow from resume upload to a submitted application, with the truth-check gate |
| [`job-copilot-sequence.html`](job-copilot-sequence.html) | What happens after you press Send: the apply, then the referral email (planned) |

The JSON in [`src/`](src) is the source for each diagram. To change one, edit its JSON and re-render with the Archify skill (`finalize <type> <file.json> <output.html> --quality showcase`).

These diagrams were drawn from this repo's docs and the plan in the README. They are not checked line by line against the code. Anything marked PLANNED or drawn with a dashed purple line is not built yet.
