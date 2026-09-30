#!/usr/bin/env python3
"""Sync Confluence Server/Data Center pages into a compact local Markdown snapshot. No AI involved.

    export CONFLUENCE_URL=https://confluence.example.com
    export CONFLUENCE_PAT=...            # Personal Access Token (never written to disk)
    python confluence_sync.py --space QA --space PROD
    python confluence_sync.py --page "https://confluence.example.com/pages/viewpage.action?pageId=123" --max-depth 2

Incremental: only pages whose version changed since the last run are downloaded.
Output (default qa-knowledge/confluence/): pages/<id>-<slug>.md and index.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cc_common import (
    DEFAULT_CONFIG, DEFAULT_OUT, display_space, jira_keys, load_config, load_index, parse_ref, resolve_refs,
    slugify, write_index,
)
from storage_to_md import convert

RETRY_STATUS = {429, 500, 502, 503, 504}
LIST_EXPAND = "version,ancestors,metadata.labels"
INTRO_WORDS = 40


class ConfluenceError(RuntimeError):
    pass


def urllib_transport(cafile: str | None):
    context = ssl.create_default_context(cafile=cafile) if cafile else None

    def transport(url: str, headers: dict) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60, context=context) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read() or b""

    return transport


class Client:
    def __init__(self, base_url: str, token: str, transport=None, sleep=time.sleep, retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._transport = transport or urllib_transport(None)
        self._sleep = sleep
        self._retries = retries

    def get_json(self, path: str, params: dict | None = None) -> dict:
        url = self.base_url + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        for attempt in range(self._retries + 1):
            status, headers, body = self._transport(url, self._headers)
            if status == 200:
                return json.loads(body)
            if status in RETRY_STATUS and attempt < self._retries:
                retry_after = headers.get("Retry-After") or headers.get("retry-after")
                self._sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            if status in (401, 403):
                raise ConfluenceError(f"HTTP {status} for {path}: check CONFLUENCE_PAT and your access to the space")
            raise ConfluenceError(f"HTTP {status} for {path}: {body[:200].decode('utf-8', 'replace')}")
        raise ConfluenceError(f"giving up on {path} after {self._retries} retries")

    def list_pages(self, space: str) -> list[dict]:
        pages, start = [], 0
        while True:
            data = self.get_json("/rest/api/content", {
                "spaceKey": space, "type": "page", "status": "current",
                "limit": 100, "start": start, "expand": LIST_EXPAND,
            })
            results = data.get("results", [])
            pages.extend(results)
            if not results or "next" not in data.get("_links", {}):
                return pages
            start += len(results)

    def page(self, page_id: str) -> dict:
        return self.get_json(f"/rest/api/content/{page_id}", {"expand": LIST_EXPAND + ",space"})

    def search(self, cql: str) -> list[dict]:
        """CQL search (DC /rest/api/content/search), all result pages."""
        pages, start = [], 0
        while True:
            data = self.get_json("/rest/api/content/search", {
                "cql": cql, "limit": 100, "start": start, "expand": LIST_EXPAND + ",space"})
            results = data.get("results", [])
            pages.extend(results)
            if not results or "next" not in data.get("_links", {}):
                return pages
            start += len(results)

    def page_body(self, page_id: str) -> str:
        data = self.get_json(f"/rest/api/content/{page_id}", {"expand": "body.storage"})
        return data["body"]["storage"]["value"]


def page_meta(raw: dict, space: str, base_url: str) -> dict:
    """Listing fields that can change without a version bump (moves, labels) — refreshed every run."""
    ancestors = raw.get("ancestors") or []
    labels = (raw.get("metadata") or {}).get("labels", {}).get("results", [])
    webui = (raw.get("_links") or {}).get("webui") or f"/pages/viewpage.action?pageId={raw['id']}"
    return {
        "id": str(raw["id"]),
        "title": raw["title"],
        "space": (raw.get("space") or {}).get("key") or space,
        "path": [a["title"] for a in ancestors],
        "ancestors": [str(a["id"]) for a in ancestors],
        "labels": [lbl["name"] for lbl in labels],
        "version": raw.get("version", {}).get("number", 0),
        "updated": (raw.get("version", {}).get("when") or "")[:10],
        "url": base_url + webui,
    }


def in_scope(meta: dict, roots: set[str], max_depth: int | None) -> bool:
    if not roots:
        return True
    if meta["id"] in roots:
        return True
    for i, ancestor in enumerate(meta["ancestors"]):
        if ancestor in roots:
            return max_depth is None or len(meta["ancestors"]) - i <= max_depth
    return False


def render_page(meta: dict, markdown: str) -> str:
    fields = {
        "id": meta["id"], "title": meta["title"], "path": " > ".join(meta["path"]),
        "labels": ", ".join(meta["labels"]), "updated": meta["updated"], "url": meta["url"],
        "jira": ", ".join(meta["jira"] or []),
    }
    head = [f"{k}: {v}" for k, v in fields.items() if v]  # empty fields only cost tokens
    return "---\n" + "\n".join(head) + "\n---\n\n# " + meta["title"] + "\n\n" + markdown + "\n"


def fetch_page_sources(client: Client, refs, max_depth: int | None, log=print) -> dict[str, dict]:
    """Pages given directly (id, URL, /display/SPACE/Title URL or title) plus their subtrees, from any space."""
    found: dict[str, dict] = {}
    for ref in refs:
        kind, value = parse_ref(ref)
        if kind == "id":
            try:
                roots = [client.page(value)]
            except ConfluenceError as e:
                log(f"warning: page '{ref}' not readable: {e}")
                continue
        else:
            space = display_space(str(ref))
            cql = f'type=page and title="{_cql_escape(value)}"' + (f' and space="{space}"' if space else "")
            roots = client.search(cql)
            if not roots:
                log(f"warning: page '{ref}' not found")
                continue
        for root in roots:
            rid = str(root["id"])
            found[rid] = page_meta(root, "", client.base_url)
            for raw in client.search(f"type=page and ancestor={rid}"):
                meta = page_meta(raw, "", client.base_url)
                if in_scope(meta, {rid}, max_depth):
                    found[meta["id"]] = meta
    return found


def _cql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def sync(client: Client, spaces: list[str], out: Path, roots=(), max_depth=None, full=False,
         workers: int = 4, jira_projects=None, log=print, pages=()) -> dict:
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    old_index = load_index(out / "index.jsonl")

    listed: dict[str, dict] = {}
    for space in spaces:
        raw_pages = client.list_pages(space)
        log(f"{space}: {len(raw_pages)} pages listed")
        for raw in raw_pages:
            meta = page_meta(raw, space, client.base_url)
            listed[meta["id"]] = meta

    root_ids, missing = resolve_refs(roots, listed)
    for ref in missing:
        log(f"warning: root '{ref}' not found in spaces {', '.join(spaces)}")
    if roots and not root_ids:
        raise ConfluenceError("none of the configured roots were found; nothing to sync")
    scope = {pid: m for pid, m in listed.items() if in_scope(m, set(root_ids), max_depth)}
    if pages:
        direct = fetch_page_sources(client, pages, max_depth, log)
        log(f"{len(direct)} pages from {len(pages)} page link(s)")
        if not direct and not spaces:
            raise ConfluenceError("none of the configured pages were found; nothing to sync")
        listed.update(direct)
        scope.update(direct)

    to_fetch = [
        pid for pid, m in scope.items()
        if full or pid not in old_index or old_index[pid].get("version") != m["version"]
        or not (out / old_index[pid]["file"]).is_file()
    ]
    log(f"{len(scope)} pages in scope, {len(to_fetch)} to download")

    def fetch(pid: str):
        return pid, convert(client.page_body(pid))

    fetched = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for n, (pid, converted) in enumerate(pool.map(fetch, to_fetch), 1):
            fetched[pid] = converted
            if n % 50 == 0:
                log(f"  downloaded {n}/{len(to_fetch)}")

    title_to_id = {m["title"]: pid for pid, m in listed.items()}
    index: dict[str, dict] = {}
    for pid, meta in scope.items():
        entry = dict(meta)
        if pid in fetched:
            c = fetched[pid]
            words = c.markdown.split()
            entry.update(
                headings=c.headings,
                jira=list(dict.fromkeys(c.jira_macro_keys + jira_keys(c.markdown, jira_projects))),
                link_titles=c.link_titles,
                words=len(words),
                intro=_intro(c.markdown),
            )
            body = c.markdown
        else:
            prev = old_index[pid]
            entry.update({k: prev.get(k) for k in ("headings", "jira", "link_titles", "words", "intro")})
            body = None
        entry["links"] = [title_to_id[t] for t in entry["link_titles"] or [] if t in title_to_id]
        entry["file"] = f"pages/{pid}-{slugify(meta['title'])}.md"

        old_file = old_index.get(pid, {}).get("file")
        if body is None and old_file and old_file != entry["file"]:
            body = _read_body(out / old_file)  # renamed page: move the file
        if old_file and old_file != entry["file"]:
            (out / old_file).unlink(missing_ok=True)
        if body is not None:
            (out / entry["file"]).write_text(render_page(entry, body), encoding="utf-8")
        elif old_file:
            # metadata may have changed (path/labels); rewrite the header cheaply
            existing = _read_body(out / entry["file"])
            (out / entry["file"]).write_text(render_page(entry, existing), encoding="utf-8")
        index[pid] = entry

    removed = [pid for pid in old_index if pid not in index]
    for pid in removed:
        (out / old_index[pid]["file"]).unlink(missing_ok=True)

    write_index(out / "index.jsonl", index)
    stats = {"listed": len(listed), "in_scope": len(index), "downloaded": len(fetched), "removed": len(removed)}
    log(f"done: {stats['downloaded']} downloaded, {len(index) - len(fetched)} unchanged, {len(removed)} removed")
    return stats


def _intro(markdown: str) -> str:
    """First words of body text (not headings/tables) — a cheap summary for matching and review."""
    words: list[str] = []
    for line in markdown.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "```")):
            continue
        words.extend(s.lstrip("-*> ").split())
        if len(words) >= INTRO_WORDS:
            break
    return " ".join(words[:INTRO_WORDS])


def _read_body(path: Path) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    # strip the frontmatter + "# title" header written by render_page
    parts = text.split("\n---\n", 1)
    body = parts[1] if len(parts) == 2 else text
    lines = body.lstrip("\n").split("\n", 2)
    return lines[2].strip() if len(lines) == 3 and lines[0].startswith("# ") else body.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"TOML config (default {DEFAULT_CONFIG})")
    parser.add_argument("--space", action="append", help="space key (repeatable; overrides config)")
    parser.add_argument("--page", action="append",
                        help="sync this page and its subtree from any space: URL, id or title (repeatable)")
    parser.add_argument("--root", action="append", help="within --space, only sync this subtree (repeatable)")
    parser.add_argument("--max-depth", type=int, help="max depth below roots")
    parser.add_argument("--out", help=f"output dir (default {DEFAULT_OUT}/confluence)")
    parser.add_argument("--full", action="store_true", help="re-download every page")
    parser.add_argument("--workers", type=int, default=4, help="parallel downloads (default 4)")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config)).get("confluence", {})
    base_url = os.environ.get("CONFLUENCE_URL") or cfg.get("base_url")
    token = os.environ.get("CONFLUENCE_PAT")
    spaces = args.space or cfg.get("spaces") or []
    page_refs = args.page or cfg.get("pages") or []
    if args.page and not args.space:
        spaces = []  # explicit --page on the command line: only those pages
    if not base_url or not token or not (spaces or page_refs):
        print("need CONFLUENCE_URL (or [confluence].base_url), CONFLUENCE_PAT env var, and --space/--page or "
              "[confluence].spaces/pages", file=sys.stderr)
        return 2
    out = Path(args.out or cfg.get("out_dir") or f"{DEFAULT_OUT}/confluence")
    transport = urllib_transport(os.environ.get("CONFLUENCE_CA_BUNDLE") or cfg.get("ca_bundle"))
    client = Client(base_url, token, transport)
    try:
        sync(client, spaces, out,
             roots=args.root or cfg.get("roots") or [],
             max_depth=args.max_depth if args.max_depth is not None else cfg.get("max_depth"),
             full=args.full, workers=args.workers, jira_projects=cfg.get("jira_projects"), pages=page_refs)
    except (ConfluenceError, urllib.error.URLError, ssl.SSLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
