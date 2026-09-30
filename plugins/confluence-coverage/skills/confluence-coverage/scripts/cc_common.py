"""Helpers shared by confluence_sync.py and coverage_map.py (standard library only)."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote_plus

if sys.version_info < (3, 11):
    sys.exit("Python 3.11+ is required (uses tomllib).")

import tomllib  # noqa: E402

DEFAULT_CONFIG = "confluence-coverage.toml"
DEFAULT_OUT = "qa-knowledge"

JIRA_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-(\d{1,6})\b")
# Uppercase-dash-number tokens that are standards, not Jira keys.
NOT_JIRA = {
    "AES", "API", "CVE", "EN", "ES", "GDPR", "GPT", "HTTP", "HTTPS", "IEC", "IEEE", "ISO", "JDK", "MP",
    "OWASP", "PCI", "RFC", "RSA", "SHA", "SSL", "TCP", "TLS", "UDP", "UTF", "WCAG", "X",
}
PAGE_ID_RE = re.compile(r"(?:[?&]pageId=|/pages/)(\d+)")
DISPLAY_RE = re.compile(r"/display/[^/]+/([^?#]+)")


def jira_keys(text: str, projects: list[str] | None = None) -> list[str]:
    """Jira issue keys in ``text``, in first-seen order. ``projects`` restricts to those prefixes."""
    allowed = set(projects) if projects else None
    seen: dict[str, None] = {}
    for m in JIRA_RE.finditer(text):
        prefix = m.group(1)
        if (allowed is not None and prefix not in allowed) or (allowed is None and prefix in NOT_JIRA):
            continue
        seen.setdefault(m.group(0), None)
    return list(seen)


def slugify(title: str, max_len: int = 60) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "page"


def norm_title(title: str) -> str:
    return " ".join(title.casefold().split())


def display_space(ref: str) -> str | None:
    """Space key from a /display/SPACE/Title URL, else None."""
    m = re.search(r"/display/([^/]+)/", ref)
    return unquote_plus(m.group(1)) if m else None


def parse_ref(ref) -> tuple[str, str]:
    """A page reference from config: numeric id, page URL, /display/ URL, or exact title."""
    s = str(ref).strip()
    if s.isdigit():
        return "id", s
    m = PAGE_ID_RE.search(s)
    if m:
        return "id", m.group(1)
    m = DISPLAY_RE.search(s)
    if m:
        return "title", unquote_plus(m.group(1))
    return "title", s


def resolve_refs(refs, pages: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Resolve config refs against known pages. Returns (page ids, refs that matched nothing)."""
    by_title: dict[str, list[str]] = {}
    for pid, page in pages.items():
        by_title.setdefault(norm_title(page["title"]), []).append(pid)
    ids: list[str] = []
    missing: list[str] = []
    for ref in refs or []:
        kind, value = parse_ref(ref)
        found = [value] if kind == "id" and value in pages else by_title.get(norm_title(value), [])
        if found:
            ids.extend(i for i in found if i not in ids)
        else:
            missing.append(str(ref))
    return ids, missing


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_index(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    pages = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            pages[entry["id"]] = entry
    return pages


def write_index(path: Path, pages: dict[str, dict]) -> None:
    lines = [json.dumps(pages[pid], ensure_ascii=False, separators=(",", ":")) for pid in sorted(pages, key=int)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
