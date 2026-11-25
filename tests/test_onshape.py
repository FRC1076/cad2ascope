"""Phase 4: the Onshape client and `fetch`, against a fake server (no network, no keys)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from cad2ascope.cli import main
from cad2ascope.errors import CadError
from cad2ascope.onshape import EXPORT_PARAMS, Client, fetch, parse_url
from test_fixtures import FIXTURES

DID, WID, EID, VID = "a" * 24, "b" * 24, "c" * 24, "d" * 24
URL = f"https://team.onshape.com/documents/{DID}/w/{WID}/e/{EID}"
ACCESS, SECRET = "ACCESSKEY1234567890", "SECRETKEY0987654321"


class Resp:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code, self._body, self.headers, self._content = status, body, headers or {}, content

    def json(self):
        return self._body

    def iter_content(self, chunk_size=1):
        yield self._content


class FakeOnshape:
    """Answers the five endpoints cad2ascope uses. ``script`` overrides responses per (method, path regex)."""

    def __init__(self, versions=None, polls=2, fail=None, zip_bytes=b"PK-zip", script=None):
        self.versions = (
            versions
            if versions is not None
            else [
                {"id": "0" * 24, "name": "Start", "createdAt": "2026-01-01T00:00:00Z"},
                {"id": VID, "name": "Week 4", "createdAt": "2026-11-20T00:00:00Z"},
                {"id": "e" * 24, "name": "Week 3", "createdAt": "2026-11-10T00:00:00Z"},
            ]
        )
        self.polls, self.fail, self.zip_bytes = polls, fail, zip_bytes
        self.script = script or {}
        self.calls: list[tuple[str, str, dict]] = []
        self.auths = set()

    def request(self, method, url, auth=None, timeout=None, params=None, json=None, stream=False):
        path = url.split("/api/v10", 1)[1]
        self.calls.append((method, path, json or params or {}))
        self.auths.add(auth)
        for (m, pat), responses in self.script.items():
            if m == method and re.fullmatch(pat, path) and responses:
                return responses.pop(0)
        if method == "GET" and path == f"/documents/d/{DID}/versions":
            offset, limit = (params or {}).get("offset", 0), (params or {}).get("limit", 0)
            if limit > 20:  # the real server answers 400 above the spec's maximum
                return Resp(400, {"message": "limit too large"})
            return Resp(body=self.versions[offset : offset + (limit or len(self.versions))])
        if method == "GET" and path == f"/documents/d/{DID}/w/{WID}/currentmicroversion":
            return Resp(body={"microversion": "f" * 24})
        if method == "POST" and re.fullmatch(rf"/assemblies/d/{DID}/[wv]/[0-9a-f]{{24}}/e/{EID}/translations", path):
            return Resp(body={"id": "t1", "requestState": "ACTIVE"})
        if method == "GET" and path == "/translations/t1":
            self.polls -= 1
            if self.polls > 0:
                return Resp(body={"id": "t1", "requestState": "ACTIVE"})
            if self.fail:
                return Resp(body={"id": "t1", "requestState": "FAILED", "failureReason": self.fail})
            return Resp(body={"id": "t1", "requestState": "DONE", "resultExternalDataIds": ["x1"]})
        if method == "GET" and path == f"/documents/d/{DID}/externaldata/x1":
            return Resp(content=self.zip_bytes)
        return Resp(404, {"message": "not found"})


def client(server, clock=None):
    t = [0.0]

    def tick():
        t[0] += 1.0
        return t[0]

    return Client("https://team.onshape.com", ACCESS, SECRET, session=server, sleep=lambda s: None, clock=clock or tick)


def test_parse_url():
    ref = parse_url(URL)
    assert (ref.base, ref.did, ref.wvm, ref.wvmid, ref.eid) == ("https://team.onshape.com", DID, "w", WID, EID)
    with pytest.raises(CadError, match="copy the whole address"):
        parse_url("https://team.onshape.com/documents/123")


def test_latest_version_export_and_download(tmp_path):
    server = FakeOnshape()
    got = fetch(URL, "latest", "Export=AdvantageScope", cache_dir=tmp_path, client=client(server))
    assert not got.cached and got.zip_path.read_bytes() == b"PK-zip"
    assert got.source["version_name"] == "Week 4" and got.source["version_id"] == VID
    methods = [(m, p) for m, p, _ in server.calls]
    assert methods[0] == ("GET", f"/documents/d/{DID}/versions")
    assert methods[1] == ("POST", f"/assemblies/d/{DID}/v/{VID}/e/{EID}/translations")
    body = server.calls[1][2]
    assert body == {**EXPORT_PARAMS, "configuration": "Export=AdvantageScope"}
    assert body["storeInDocument"] is False  # download only: a store would be a write
    assert got.calls == len(server.calls) == 5  # versions, POST, 2 polls, download
    assert server.auths == {(ACCESS, SECRET)}
    meta = json.loads(got.zip_path.with_suffix(".json").read_text())
    assert meta["api_calls"] == 5 and ACCESS not in json.dumps(meta) and SECRET not in json.dumps(meta)


def test_same_version_again_is_one_call(tmp_path):
    fetch(URL, "latest", cache_dir=tmp_path, client=client(FakeOnshape()))
    server = FakeOnshape()
    got = fetch(URL, "latest", cache_dir=tmp_path, client=client(server))
    assert got.cached and got.calls == 1 and [p for _, p, _ in server.calls] == [f"/documents/d/{DID}/versions"]
    assert got.source["translation_id"] == "t1"  # metadata from the original export


def test_new_version_or_configuration_exports_again(tmp_path):
    fetch(URL, "latest", cache_dir=tmp_path, client=client(FakeOnshape()))
    got = fetch(URL, "Week 3", cache_dir=tmp_path, client=client(FakeOnshape()))
    assert not got.cached and got.source["version_name"] == "Week 3"
    got = fetch(URL, "latest", "Export=Full", cache_dir=tmp_path, client=client(FakeOnshape()))
    assert not got.cached


def test_named_version_missing_lists_recent(tmp_path):
    with pytest.raises(CadError, match=r"no Version named 'Week 9'.*'Week 4', 'Week 3'"):
        fetch(URL, "Week 9", cache_dir=tmp_path, client=client(FakeOnshape()))


def test_only_start_version_explains_what_to_do(tmp_path):
    server = FakeOnshape(versions=[{"id": "0" * 24, "name": "Start", "createdAt": "2026-01-01"}])
    with pytest.raises(CadError, match="no Versions yet.*--workspace"):
        fetch(URL, "latest", cache_dir=tmp_path, client=client(server))


def test_workspace_preview_caches_by_microversion(tmp_path):
    server = FakeOnshape()
    got = fetch(URL, workspace=True, cache_dir=tmp_path, client=client(server))
    assert (
        got.source["kind"] == "workspace" and server.calls[1][1] == f"/assemblies/d/{DID}/w/{WID}/e/{EID}/translations"
    )
    again = fetch(URL, workspace=True, cache_dir=tmp_path, client=client(FakeOnshape()))
    assert again.cached and again.calls == 1


def test_failed_translation_tells_student_what_to_fix(tmp_path):
    with pytest.raises(CadError, match="could not export the assembly as URDF \\(Assembly has errors\\)"):
        fetch(URL, cache_dir=tmp_path, client=client(FakeOnshape(fail="Assembly has errors")))
    assert not list(tmp_path.glob("*.zip"))


def test_rate_limit_is_retried(tmp_path):
    waits = []
    server = FakeOnshape(script={("GET", f"/documents/d/{DID}/versions"): [Resp(429, headers={"Retry-After": "3"})]})
    c = Client(
        "https://team.onshape.com", ACCESS, SECRET, session=server, sleep=waits.append, clock=iter(range(1000)).__next__
    )
    got = fetch(URL, cache_dir=tmp_path, client=c)
    assert not got.cached and 3.0 in waits
    assert got.calls == 6  # the retry counts as a call


@pytest.mark.parametrize(
    ("status", "needle"),
    [(401, "rejected the API key"), (403, "shared with the account"), (404, "Check robot.onshape_url")],
)
def test_http_errors_are_explained_without_keys(tmp_path, status, needle):
    server = FakeOnshape(script={("GET", f"/documents/d/{DID}/versions"): [Resp(status)]})
    with pytest.raises(CadError) as err:
        fetch(URL, cache_dir=tmp_path, client=client(server))
    assert needle in str(err.value)
    assert ACCESS not in str(err.value) and SECRET not in str(err.value)


def test_poll_timeout(tmp_path):
    server = FakeOnshape(polls=10**9)
    c = Client(
        "https://team.onshape.com",
        ACCESS,
        SECRET,
        session=server,
        sleep=lambda s: None,
        clock=iter(range(0, 10**7, 60)).__next__,
    )
    with pytest.raises(CadError, match="did not finish in 20 minutes"):
        fetch(URL, cache_dir=tmp_path, client=c)


def test_missing_keys_explain_the_no_key_route(tmp_path, monkeypatch):
    monkeypatch.delenv("ONSHAPE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("ONSHAPE_SECRET_KEY", raising=False)
    with pytest.raises(CadError, match="source scripts/onshape-env.sh.*cad2ascope build"):
        fetch(URL, cache_dir=tmp_path)


def _zip_of(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.name not in ("advantagescope.yaml", "expected.json"):
                z.write(p, p.relative_to(folder))
    return buf.getvalue()


def test_run_fetches_then_builds_and_records_the_version(tmp_path, monkeypatch, capsys):
    import cad2ascope.onshape as onshape_module

    server = FakeOnshape(zip_bytes=_zip_of(FIXTURES / "single_revolute"))
    monkeypatch.setattr(onshape_module, "Client", lambda *a, **k: client(server))
    monkeypatch.setenv("ONSHAPE_ACCESS_KEY", ACCESS)
    monkeypatch.setenv("ONSHAPE_SECRET_KEY", SECRET)
    cfg = tmp_path / "advantagescope.yaml"
    cfg.write_text(
        (FIXTURES / "single_revolute" / "advantagescope.yaml")
        .read_text()
        .replace("  origin_frame: ascope_origin\n", f"  origin_frame: ascope_origin\n  onshape_url: {URL}\n")
    )
    rc = main(
        [
            "run",
            "-c",
            str(cfg),
            "-o",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0, capsys.readouterr().err
    manifest = json.loads((tmp_path / "out" / "Robot_single_revolute" / "manifest.json").read_text())
    assert manifest["source"]["onshape"]["version_name"] == "Week 4"
    assert manifest["source"]["onshape"]["version_id"] == VID
    out = capsys.readouterr()
    assert ACCESS not in out.out + out.err and SECRET not in out.out + out.err


def test_run_without_url_or_zip_says_what_to_do(tmp_path, capsys):
    rc = main(["run", "-c", str(FIXTURES / "single_revolute" / "advantagescope.yaml"), "-o", str(tmp_path)])
    assert rc == 1 and "no robot.onshape_url" in capsys.readouterr().err


def test_run_with_dropped_zip_needs_no_key(tmp_path):
    rc = main(
        [
            "run",
            "-c",
            str(FIXTURES / "prismatic" / "advantagescope.yaml"),
            "--zip",
            str(FIXTURES / "prismatic.zip"),
            "-o",
            str(tmp_path),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0 and (tmp_path / "Robot_prismatic" / "model_0.glb").is_file()
    assert (tmp_path / "src/main/java/frc/robot/generated/RobotModel.java").is_file()


def test_versions_are_paged_within_the_server_limit(tmp_path):
    many = [
        {"id": f"{i:024x}", "name": f"v{i}", "createdAt": f"2026-11-{i % 28 + 1:02d}T{i % 24:02d}:00:00Z"}
        for i in range(45)
    ]
    server = FakeOnshape(versions=many)
    got = fetch(URL, "v44", cache_dir=tmp_path, client=client(server))
    pages = [c for c in server.calls if c[1].endswith("/versions")]
    assert len(pages) == 3 and all(c[2]["limit"] == 20 for c in pages)
    assert got.source["version_name"] == "v44"
