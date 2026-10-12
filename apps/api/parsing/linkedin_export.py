"""LinkedIn data-export ZIP -> fact DRAFTS (NEXT-WORK-PLAN §5.1).

Deterministic, no model call: the export is already structured. Output goes into the same
review flow as a parsed resume, so nothing becomes a fact until the user confirms it.

The ZIP is untrusted input and is never extracted to disk; only the three CSVs we want are
read, each through a bounded stream, so a declared size can't lie its way past the cap.
Column names are matched case-insensitively and missing ones are tolerated: they come from
LinkedIn's archive format as remembered, not from a spec LinkedIn publishes.
"""
import csv
import io
import posixpath
import zipfile

from schemas import ApplicantBasics

MAX_ENTRIES = 2000                     # a full archive is ~100 files
MAX_CSV_BYTES = 2 * 1024 * 1024        # decompressed, per file we read
WANTED = ("profile", "positions", "skills")


class ExportRejected(ValueError):
    """The upload is not a LinkedIn export we will read. Message is user-safe."""


def _safe_name(name: str) -> bool:
    if "\\" in name or name.startswith("/") or ":" in name:
        return False
    return ".." not in posixpath.normpath(name).split("/")


def _pick(names: list[str], key: str) -> str | None:
    """Partial, case-insensitive match on the file name; shortest wins, so
    `Profile.csv` beats `Profile Summary.csv`."""
    hits = [n for n in names if n.lower().endswith(".csv") and key in posixpath.basename(n).lower()]
    return min(hits, key=lambda n: len(posixpath.basename(n))) if hits else None


def _rows(zf: zipfile.ZipFile, name: str | None, header_key: str) -> list[dict]:
    if name is None:
        return []
    with zf.open(name) as fh:
        data = fh.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise ExportRejected("This export has a file too large to read.")
    lines = data.decode("utf-8-sig", errors="replace").splitlines(keepends=True)
    # Some LinkedIn CSVs open with "Notes:" lines before the header.
    start = next((i for i, line in enumerate(lines) if header_key in line.lower()), None)
    if start is None:
        return []
    reader = csv.DictReader(io.StringIO("".join(lines[start:])))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def read_linkedin_export(raw: bytes) -> tuple[list[dict], ApplicantBasics | None]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ExportRejected("This is not a valid ZIP file.") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ExportRejected("This ZIP has too many files to be a LinkedIn export.")
        if not all(_safe_name(i.filename) for i in infos):
            raise ExportRejected("This ZIP contains unsafe file paths.")
        names = [i.filename for i in infos if not i.is_dir()]
        try:
            profile = _rows(zf, _pick(names, "profile"), "first name")
            positions = _rows(zf, _pick(names, "positions"), "company name")
            skills = _rows(zf, _pick(names, "skills"), "name")
        except (RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
            # Encrypted entry, corrupt stream, or unsupported compression.
            raise ExportRejected("This ZIP could not be read.") from exc

    facts: list[dict] = []
    for p in positions:
        title, company = p.get("title"), p.get("company name")
        if not (title and company):
            continue
        dates = ""
        if p.get("started on"):
            dates = f" ({p['started on']} to {p.get('finished on') or 'present'})"
        role = f"{title}, {company}"
        facts.append({"category": "experience", "achievement": f"{title} at {company}{dates}",
                      "proof": company, "metric": None, "tags": []})
        for line in (p.get("description") or "").splitlines():
            line = line.strip().lstrip("-•* ").strip()
            if line:
                facts.append({"category": "experience", "achievement": line,
                              "proof": role, "metric": None, "tags": []})
    for s in skills:
        if s.get("name"):
            facts.append({"category": "skill", "achievement": s["name"], "proof": "LinkedIn skills",
                          "metric": None, "tags": [s["name"]]})

    basics = None
    if profile:
        name = " ".join(x for x in (profile[0].get("first name"), profile[0].get("last name")) if x)
        try:
            basics = ApplicantBasics(full_name=name) if name else None
        except ValueError:
            basics = None

    if not facts and basics is None:
        raise ExportRejected("No profile, positions or skills found in this ZIP.")
    return facts, basics
