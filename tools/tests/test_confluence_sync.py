import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

from cc_common import load_index
from confluence_sync import Client, ConfluenceError, sync

BASE = "https://confluence.test"
TOKEN = "secret-pat-123"


class FakeConfluence:
    """Minimal DC REST v1: paginated /rest/api/content listing + /rest/api/content/{id} bodies."""

    def __init__(self, page_size=2):
        self.page_size = page_size
        self.pages = {}
        self.body_calls = []
        self.fail_next = []  # list of (status, headers) returned before normal responses
        self.cql_calls = []

    def add(self, pid, title, body, ancestors=(), version=1, labels=(), updated="2026-01-01"):
        self.pages[pid] = {"title": title, "body": body, "ancestors": list(ancestors),
                           "version": version, "labels": list(labels), "updated": updated}

    def __call__(self, url, headers):
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        if self.fail_next:
            status, h = self.fail_next.pop(0)
            return status, h, b"busy"
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/rest/api/content":
            start = int(q["start"])
            ids = sorted(self.pages, key=int)
            chunk = ids[start:start + self.page_size]
            data = {"results": [self._meta(pid) for pid in chunk], "_links": {}}
            if start + self.page_size < len(ids):
                data["_links"]["next"] = "/rest/api/content?next"
            return 200, {}, json.dumps(data).encode()
        if u.path == "/rest/api/content/search":
            self.cql_calls.append(q["cql"])
            ids = self._cql(q["cql"])
            return 200, {}, json.dumps({"results": [self._meta(pid) for pid in ids], "_links": {}}).encode()
        pid = u.path.rsplit("/", 1)[1]
        if pid not in self.pages:
            return 404, {}, b"not found"
        if "body.storage" not in q.get("expand", ""):
            return 200, {}, json.dumps(self._meta(pid)).encode()
        self.body_calls.append(pid)
        return 200, {}, json.dumps({"id": pid, "body": {"storage": {"value": self.pages[pid]["body"]}}}).encode()

    def _cql(self, cql):
        if m := re.search(r"ancestor=(\d+)", cql):
            return [pid for pid, p in self.pages.items() if m.group(1) in p["ancestors"]]
        m = re.search(r'title="((?:[^"\\]|\\.)*)"', cql)
        title = m.group(1).replace('\\"', '"')
        space = re.search(r'space="([^"]+)"', cql)
        return [pid for pid, p in self.pages.items() if p["title"] == title and (not space or space.group(1) == "KEY")]

    def _meta(self, pid):
        p = self.pages[pid]
        return {
            "id": pid, "title": p["title"],
            "version": {"number": p["version"], "when": p["updated"] + "T10:00:00.000Z"},
            "ancestors": [{"id": a, "title": self.pages[a]["title"]} for a in p["ancestors"]],
            "metadata": {"labels": {"results": [{"name": n} for n in p["labels"]]}},
            "_links": {"webui": f"/pages/viewpage.action?pageId={pid}"},
            "space": {"key": "KEY"},
        }


@pytest.fixture
def fake():
    f = FakeConfluence()
    f.add("1", "Product", "<p>Root</p>")
    f.add("2", "Payments v2", "<h2>Flows</h2><p>Pay by card PAY-1. See "
                              '<ac:link><ri:page ri:content-title="Refunds" /></ac:link></p>', ancestors=["1"])
    f.add("3", "Refunds", "<p>Refund within 14 days.</p>", ancestors=["1", "2"], labels=["feature"])
    f.add("4", "QA", "<p>QA home</p>")
    f.add("5", "Test plan Payments", "<p>Plan</p>", ancestors=["4"])
    return f


def run(fake, out, **kw):
    client = Client(BASE, TOKEN, transport=fake, sleep=lambda s: None)
    return sync(client, ["KEY"], out, log=lambda m: None, **kw)


def test_first_sync_writes_snapshot(fake, tmp_path):
    stats = run(fake, tmp_path)

    assert stats == {"listed": 5, "in_scope": 5, "downloaded": 5, "removed": 0}
    index = load_index(tmp_path / "index.jsonl")
    p2 = index["2"]
    assert p2["path"] == ["Product"] and p2["ancestors"] == ["1"]
    assert p2["headings"] == ["Flows"]
    assert p2["jira"] == ["PAY-1"]
    assert p2["links"] == ["3"]  # link title resolved to page id
    assert p2["url"] == f"{BASE}/pages/viewpage.action?pageId=2"
    assert index["3"]["labels"] == ["feature"]
    text = (tmp_path / p2["file"]).read_text()
    assert p2["file"] == "pages/2-payments-v2.md"
    assert "title: Payments v2\npath: Product\n" in text
    assert "# Payments v2\n\n## Flows\n\nPay by card PAY-1. See [[Refunds]]" in text


def test_second_sync_downloads_only_changed_pages(fake, tmp_path):
    run(fake, tmp_path)
    fake.body_calls.clear()

    assert run(fake, tmp_path)["downloaded"] == 0

    fake.pages["3"].update(version=2, body="<p>Refund within 30 days.</p>")
    assert run(fake, tmp_path)["downloaded"] == 1
    assert fake.body_calls == ["3"]
    assert "30 days" in (tmp_path / "pages/3-refunds.md").read_text()


def test_deleted_and_renamed_pages(fake, tmp_path):
    run(fake, tmp_path)
    del fake.pages["5"]
    fake.pages["3"]["title"] = "Refunds and returns"  # rename without version bump

    stats = run(fake, tmp_path)

    assert stats["removed"] == 1
    assert not (tmp_path / "pages/5-test-plan-payments.md").exists()
    assert not (tmp_path / "pages/3-refunds.md").exists()
    renamed = (tmp_path / "pages/3-refunds-and-returns.md").read_text()
    assert "title: Refunds and returns" in renamed and "Refund within 14 days." in renamed


def test_roots_and_max_depth(fake, tmp_path):
    stats = run(fake, tmp_path, roots=["Product"], max_depth=1)
    assert set(load_index(tmp_path / "index.jsonl")) == {"1", "2"}
    assert stats["downloaded"] == 2


def test_root_by_url(fake, tmp_path):
    run(fake, tmp_path, roots=[f"{BASE}/pages/viewpage.action?pageId=4"])
    assert set(load_index(tmp_path / "index.jsonl")) == {"4", "5"}


def test_unknown_roots_fail(fake, tmp_path):
    with pytest.raises(ConfluenceError, match="none of the configured roots"):
        run(fake, tmp_path, roots=["Nope"])


def test_retries_on_429_with_retry_after(fake, tmp_path):
    sleeps = []
    fake.fail_next = [(429, {"Retry-After": "7"}), (503, {})]
    client = Client(BASE, TOKEN, transport=fake, sleep=sleeps.append)
    sync(client, ["KEY"], tmp_path, log=lambda m: None)
    assert sleeps == [7.0, 2]


def test_auth_error_does_not_leak_token(fake, tmp_path):
    fake.fail_next = [(401, {})]
    client = Client(BASE, TOKEN, transport=fake, sleep=lambda s: None)
    with pytest.raises(ConfluenceError) as e:
        sync(client, ["KEY"], tmp_path, log=lambda m: None)
    assert "CONFLUENCE_PAT" in str(e.value) and TOKEN not in str(e.value)


def test_token_never_written_to_disk(fake, tmp_path):
    run(fake, tmp_path)
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert TOKEN not in f.read_text()


def test_page_links_sync_subtrees_without_listing_spaces(fake, tmp_path):
    client = Client(BASE, TOKEN, transport=fake, sleep=lambda s: None)
    stats = sync(client, [], tmp_path, pages=[f"{BASE}/pages/viewpage.action?pageId=2", "QA"],
                 log=lambda m: None)

    assert set(load_index(tmp_path / "index.jsonl")) == {"2", "3", "4", "5"}
    assert stats["listed"] == 4  # no space listing happened
    assert load_index(tmp_path / "index.jsonl")["3"]["space"] == "KEY"
    assert 'type=page and title="QA"' in fake.cql_calls


def test_page_link_by_display_url_and_depth(fake, tmp_path):
    client = Client(BASE, TOKEN, transport=fake, sleep=lambda s: None)
    sync(client, [], tmp_path, pages=[f"{BASE}/display/KEY/Product"], max_depth=1, log=lambda m: None)
    assert set(load_index(tmp_path / "index.jsonl")) == {"1", "2"}
    assert 'space="KEY"' in fake.cql_calls[0]


def test_unknown_page_links_fail(fake, tmp_path):
    client = Client(BASE, TOKEN, transport=fake, sleep=lambda s: None)
    with pytest.raises(ConfluenceError, match="none of the configured pages"):
        sync(client, [], tmp_path, pages=["No such page"], log=lambda m: None)


def test_cql_title_is_escaped():
    from confluence_sync import _cql_escape
    assert _cql_escape('Say "hi" \\ bye') == 'Say \\"hi\\" \\\\ bye'
