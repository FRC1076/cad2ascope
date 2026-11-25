"""Onshape API client for `cad2ascope fetch` (PLAN §5, Phase 4).

Every call here was confirmed against the server's OpenAPI spec (Onshape 1.224) in Phase 0 (docs/phase0-findings.md,
A1, A2) and needs only the read scope, so a read-only API key is enough:

- ``GET  /api/v10/documents/d/{did}/versions``                         list versions (paginated)
- ``GET  /api/v10/documents/d/{did}/w/{wid}/currentmicroversion``      workspace state, for caching previews
- ``POST /api/v10/assemblies/d/{did}/{w|v}/{id}/e/{eid}/translations`` start the URDF export
- ``GET  /api/v10/translations/{tid}``                                 poll until DONE or FAILED
- ``GET  /api/v10/documents/d/{did}/externaldata/{fid}``               download the zip

Rules from PLAN §5: export from a Version by default (a workspace export is a preview option); cache downloads by
version, so a re-run on the same version costs one call (the version lookup) and no export; count calls; never
write keys anywhere. Keys come only from ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from cad2ascope.errors import CadError

API = "/api/v10"
URL_RE = re.compile(
    r"^(?P<base>https://[a-z0-9.\-]+\.onshape\.com)/documents/(?P<did>[0-9a-f]{24})/(?P<wvm>[wvm])/(?P<wvmid>[0-9a-f]{24})"
    r"/e/(?P<eid>[0-9a-f]{24})"
)
EXPORT_PARAMS = {
    "formatName": "URDF",
    "urdfMeshFormat": "GLTF",  # the format the converter was built and measured on (Phase 0, Phase 2)
    "resolution": "medium",
    "mergeFastenedComponents": False,  # keep it off: it hides grounded and unmated parts (Phase 0 findings)
    "storeInDocument": False,  # download; storing in the document would be a write
    "notifyUser": False,
}
RETRY_STATUS = {429, 500, 502, 503, 504}
VERSIONS_PAGE = 20  # getDocumentVersions: limit maximum 20 (OpenAPI spec)
MAX_TRIES = 5
POLL_START_S = 2.0
POLL_MAX_S = 15.0
POLL_TIMEOUT_S = 20 * 60


@dataclass(frozen=True)
class DocRef:
    base: str
    did: str
    wvm: str
    wvmid: str
    eid: str


def parse_url(url: str) -> DocRef:
    m = URL_RE.match(url.strip())
    if not m:
        raise CadError(
            f"robot.onshape_url does not look like an Onshape assembly link: {url!r}. Open the main assembly tab in "
            "Onshape and copy the whole address from the browser."
        )
    return DocRef(m["base"], m["did"], m["wvm"], m["wvmid"], m["eid"])


def credentials() -> tuple[str, str]:
    access, secret = os.environ.get("ONSHAPE_ACCESS_KEY", ""), os.environ.get("ONSHAPE_SECRET_KEY", "")
    if not access or not secret:
        raise CadError(
            "ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY are not set. On a Mac, run 'source scripts/onshape-env.sh' "
            "first; in GitHub Actions, add them as repository secrets. Without a key, export a URDF zip from Onshape "
            "by hand and pass it to 'cad2ascope build' instead."
        )
    return access, secret


class Client:
    """Minimal Onshape REST client with retries and a call counter. ``session``, ``sleep`` and ``clock`` are
    injectable so tests can run against a fake server without waiting."""

    def __init__(self, base: str, access: str, secret: str, session=None, sleep=time.sleep, clock=time.monotonic):
        self.base = base.rstrip("/")
        self._auth = (access, secret)
        self._session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self.calls = 0

    def _request(self, method: str, path: str, **kw) -> requests.Response:
        url = f"{self.base}{API}{path}"
        delay = 1.0
        for attempt in range(MAX_TRIES):
            self.calls += 1
            try:
                resp = self._session.request(method, url, auth=self._auth, timeout=60, **kw)
            except requests.RequestException as e:
                if attempt == MAX_TRIES - 1:
                    raise CadError(
                        f"Could not reach Onshape at {self.base} ({type(e).__name__}). Check the network and try again."
                    ) from None
                self._sleep(delay)
                delay *= 2
                continue
            if resp.status_code in RETRY_STATUS and attempt < MAX_TRIES - 1:
                wait = resp.headers.get("Retry-After")
                self._sleep(float(wait) if wait and wait.replace(".", "", 1).isdigit() else delay)
                delay *= 2
                continue
            if resp.status_code >= 400:
                raise CadError(_explain(resp.status_code, method, path))
            return resp
        raise CadError(f"Onshape kept answering with errors for {method} {path}. Try again in a few minutes.")

    def get_json(self, path: str, **kw) -> Any:
        return self._request("GET", path, **kw).json()

    # ------------------------------------------------------------------------------------------- documents

    def versions(self, did: str) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:  # the spec caps limit at 20; a larger value is a 400
            page = self.get_json(f"/documents/d/{did}/versions", params={"offset": offset, "limit": VERSIONS_PAGE})
            out += page
            if len(page) < VERSIONS_PAGE:
                return out
            offset += VERSIONS_PAGE

    def microversion(self, did: str, wid: str) -> str:
        return self.get_json(f"/documents/d/{did}/w/{wid}/currentmicroversion")["microversion"]

    # ------------------------------------------------------------------------------------------- export

    def export_urdf(self, ref: DocRef, wv: str, wvid: str, configuration: str | None, dest: Path) -> dict:
        body = dict(EXPORT_PARAMS)
        if configuration:
            body["configuration"] = configuration
        start = self._request("POST", f"/assemblies/d/{ref.did}/{wv}/{wvid}/e/{ref.eid}/translations", json=body).json()
        tid = start["id"]
        t0, wait = self._clock(), POLL_START_S
        state = start.get("requestState")
        info = start
        while state == "ACTIVE":
            if self._clock() - t0 > POLL_TIMEOUT_S:
                raise CadError(
                    f"Onshape's export did not finish in {POLL_TIMEOUT_S // 60} minutes. Try again; if it keeps "
                    "happening, export the URDF zip by hand and use 'cad2ascope build'."
                )
            self._sleep(wait)
            wait = min(POLL_MAX_S, wait * 1.5)
            info = self.get_json(f"/translations/{tid}")
            state = info.get("requestState")
        if state != "DONE":
            reason = info.get("failureReason") or "no reason given"
            raise CadError(
                f"Onshape could not export the assembly as URDF ({reason}). Open the assembly in Onshape and fix any "
                "errors shown in the feature list (red items), then create a new Version and try again."
            )
        ids = info.get("resultExternalDataIds") or []
        if not ids:
            raise CadError("Onshape finished the export but returned no file. Try again.")
        resp = self._request("GET", f"/documents/d/{ref.did}/externaldata/{ids[0]}", stream=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.replace(dest)
        return {"translation_id": tid, "seconds": round(self._clock() - t0, 1)}


def _explain(status: int, method: str, path: str) -> str:
    if status == 401:
        return (
            "Onshape rejected the API key (401). Check ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY: on a Mac, run "
            "'scripts/setup-mac.sh --store-keys' again; in GitHub, update the repository secrets."
        )
    if status in (403, 404):
        return (
            f"Onshape could not open the document ({status}). Check robot.onshape_url in the config, and that the "
            "document (or the copy you use) is shared with the account that owns the API key."
        )
    return f"Onshape answered {status} to {method} {path}. Try again; if it repeats, export the URDF zip by hand."


# ----------------------------------------------------------------------------------------------- fetch with cache


@dataclass
class FetchResult:
    zip_path: Path
    cached: bool
    calls: int
    source: dict = field(default_factory=dict)  # what was exported, for the manifest


def default_cache_dir() -> Path:
    env = os.environ.get("CAD2ASCOPE_CACHE")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "cad2ascope"


def _pick_version(versions: list[dict], wanted: str) -> dict:
    real = [v for v in versions if v.get("name") != "Start"]
    if wanted == "latest":
        if not real:
            raise CadError(
                "The document has no Versions yet (only Start). In Onshape, pose the robot at ascope_zero and create a "
                "Version (PLAN §4 C6), or run with --workspace for a quick preview."
            )
        return max(real, key=lambda v: v.get("createdAt") or "")
    matches = [v for v in versions if v.get("name") == wanted]
    if not matches:
        recent = [v.get("name") for v in sorted(real, key=lambda v: v.get("createdAt") or "", reverse=True)[:5]]
        raise CadError(
            f"There is no Version named {wanted!r} in the document. Recent Versions: {', '.join(map(repr, recent)) or 'none'}. "
            "Fix robot.version in the config, or use 'latest'."
        )
    return max(matches, key=lambda v: v.get("createdAt") or "")


def fetch(
    onshape_url: str,
    version: str = "latest",
    configuration: str | None = None,
    workspace: bool = False,
    cache_dir: Path | None = None,
    client: Client | None = None,
    log=lambda msg: None,
) -> FetchResult:
    """Export the assembly as a URDF zip, or reuse the cached zip for the same Version and settings."""
    ref = parse_url(onshape_url)
    if client is None:
        base = os.environ.get("ONSHAPE_BASE_URL") or ref.base
        client = Client(base, *credentials())
    cache_dir = cache_dir or default_cache_dir()

    if workspace:
        if ref.wvm != "w":
            raise CadError("--workspace needs robot.onshape_url to point at a workspace (a link with /w/ in it).")
        wv, wvid = "w", ref.wvmid
        state = client.microversion(ref.did, ref.wvmid)
        source = {"kind": "workspace", "workspace_id": ref.wvmid, "microversion": state}
    elif ref.wvm == "v" and version == "latest":
        wv, wvid = "v", ref.wvmid
        source = {"kind": "version", "version_id": ref.wvmid, "version_name": None}
        state = ref.wvmid
    else:
        v = _pick_version(client.versions(ref.did), version)
        wv, wvid = "v", v["id"]
        source = {
            "kind": "version",
            "version_id": v["id"],
            "version_name": v.get("name"),
            "created_at": v.get("createdAt"),
        }
        state = v["id"]
    source.update(
        {"document_id": ref.did, "element_id": ref.eid, "configuration": configuration, "export": EXPORT_PARAMS}
    )

    key_data = json.dumps(
        {"did": ref.did, "eid": ref.eid, "state": state, "cfg": configuration, "p": EXPORT_PARAMS}, sort_keys=True
    )
    key = hashlib.sha256(key_data.encode()).hexdigest()[:20]
    zip_path = cache_dir / f"{ref.did[:8]}-{key}.zip"
    meta_path = zip_path.with_suffix(".json")
    if zip_path.is_file():
        log(f"Using the cached export for this {source['kind']} ({zip_path.name}).")
        if meta_path.is_file():
            try:
                source = {**json.loads(meta_path.read_text()), **source}
            except ValueError:
                pass
        return FetchResult(zip_path, True, client.calls, source)

    label = source.get("version_name") or source["kind"]
    log(f"Exporting {label!r} from Onshape as URDF. This usually takes one to two minutes.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_dir) as tmp:
        tmp_zip = Path(tmp) / "export.zip"
        info = client.export_urdf(ref, wv, wvid, configuration, tmp_zip)
        tmp_zip.replace(zip_path)
    source.update(info)
    source["api_calls"] = client.calls
    meta_path.write_text(json.dumps(source, indent=2) + "\n")
    log(f"Exported in {info['seconds']} s with {client.calls} API calls.")
    return FetchResult(zip_path, False, client.calls, source)
