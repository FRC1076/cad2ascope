# Phase 4 notes: Onshape API fetch

`cad2ascope fetch` exports the main assembly through the Onshape API and caches the zip. `cad2ascope run` fetches, then builds; `run --zip <file>` builds from a hand-exported zip with no key (PLAN §5 no-key fallback, §8.1 zip drops). Code: `src/cad2ascope/onshape.py`.

## Behavior

- **Keys** come only from `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` and are sent as HTTP Basic auth. They are never logged, written to the cache sidecar, or put in error messages (tested). `ONSHAPE_BASE_URL` overrides the host taken from `robot.onshape_url`.
- **What gets exported:** by default a Version. `robot.version: latest` picks the newest Version other than Onshape's automatic "Start"; any other value must match a Version name exactly. If the URL is a `/v/` link, that version is used. `--workspace` exports the live workspace as a preview.
- **Export settings:** URDF, glTF meshes, medium resolution, `mergeFastenedComponents: false`, `storeInDocument: false` (download only, which needs only read access). `robot.configuration` is passed through as-is.
- **Cache:** `~/.cache/cad2ascope` (or `$CAD2ASCOPE_CACHE`, or `--cache-dir`), keyed by document, element, version ID (or workspace microversion), configuration and export settings. Running again on the same Version costs one API call (the version lookup) and no export. A `.json` sidecar records the version, translation ID, export seconds and call count; `run` copies it into `manifest.json` under `source.onshape`.
- **Polling:** first check after 2 s, then 1.5× longer each time up to 15 s, for at most 20 minutes. HTTP 429 and 5xx are retried up to 5 times, honoring `Retry-After`.
- **Errors students may see:** missing keys (with the no-key route), a rejected key (401), a document not shared with the key's owner (403/404), no Versions yet, an unknown Version name (lists recent names), and a failed export (Onshape's reason, plus a pointer to fix errors in the assembly).

## Verified against the real server (2026-11-25, 2026 copy)

- `run --workspace`: export in 82 s with 11 API calls, then build. The second run used the cache with 1 API call.
- `fetch` with `version: latest` on a document whose only Version is "Start": the "no Versions yet" message.
- `getDocumentVersions` rejects `limit` above 20 with a 400. The spec says `maximum: 20`; the first version of the client used 50. Paging now uses 20, and the test server enforces the limit.

## Not yet verified

- **Exporting from a real Version** (`/v/{vid}` in the translation path). The copies have no Versions until the student finishes the CAD sheet and creates `ascope pilot 1`. Covered by fake-server tests only.
- **`robot.configuration`.** Neither copy has an `Export` configuration yet. The value is passed to Onshape unchanged; whether Onshape wants the configuration's display name or its internal ID is checked when the first configured export runs. If it needs the encoded form, copy it from the Onshape address bar (the `configuration=` part) after selecting the `AdvantageScope` value.
- **Codegen** is not part of `run` yet (Phase 3).
