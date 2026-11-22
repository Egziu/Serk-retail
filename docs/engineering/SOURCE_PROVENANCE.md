# Source provenance

Recorded 2026-11-22 (Africa/Nairobi). Evidence commands are in `BASELINE.md`.

## Supplied archive

| Field | Value |
|---|---|
| Filename | `erpnext-develop.zip` |
| Size | 40,000,248 bytes (190,259,155 uncompressed, 7,421 entries) |
| SHA-256 | `6c751bbc9798618f6b7ec3a4e7d1ecf9cfd7e7c28db46e39212f5c00d05bbdfd` |
| Zip comment | `20b97fa800c5548da786ced57111f51c858aea36` (GitHub archive convention: source commit) |
| Top-level dir | `erpnext-develop/` |
| Safety scan | 0 path-traversal entries, 0 symlinks; 16 files with exec bits (CI helper scripts and some source files with stray +x). None executed. |
| Secret scan | No AWS/GitHub/Slack/Stripe/private-key patterns found. `.github/helper/site_config_*.json` hold CI-only throwaway DB passwords (values not reproduced). |
| Untouched reference | Original upload kept read-only; extraction at `archive-inspect/erpnext-develop/`. |

## Upstream verification — **established, not assumed**

`git fetch --depth 1 https://github.com/frappe/erpnext 20b97fa8…` succeeded; the commit is
`Merge pull request #67433 from mihir-kandoi/fix/issue-66042`, committed 2026-11-21T22:30:55Z.
`diff -rq` between the fetched tree and the extracted ZIP returned **no differences**.
Conclusion: the ZIP is byte-identical to `frappe/erpnext@20b97fa8` (branch `develop`).

The installed app `apps/erpnext` is that commit (local branch `serk-pin-20b97fa8`), with a clean
working tree (tool-generated `islands/yarn.lock` drift was reverted; see R-13).

## Frappe Framework — **inferred pairing**

ERPNext declares `frappe >=17.0.0-dev,<18.0.0` and the ZIP contains no Frappe. Selected
`frappe/frappe@fdb29e699921b59d895586b3dbea3e61baedf137` — the last `develop` commit before the
ERPNext commit time (2026-11-21T19:19:11Z). This is a **time-based pairing**, not a published
compatibility pin. Evidence of compatibility: site install, migrate, and the baseline tests in
`BASELINE.md`.

## Versions

| Component | Version | Licence (from source) |
|---|---|---|
| ERPNext | 17.0.0-dev | GPL-3.0 (`license.txt`, `package.json`) |
| Frappe | 17.0.0-dev | MIT (`LICENSE`, `pyproject.toml`) |
| SERK Retail | 0.0.1 | GPL-3.0 |

ERPNext `develop` is a **pre-release** branch. A pilot should move to a supported stable release
line (version-16 or the first version-17 release) before go-live; see R-01.

## Licence obligations (engineering summary, not legal advice)

* SERK Retail imports ERPNext Python modules and runs inside the same process. The conservative
  reading of the GPL FAQ is that it forms a combined work with ERPNext, so SERK Retail is
  released under GPL-3.0. Distribution of the app (including to franchisees or customers)
  must offer corresponding source. SaaS-only use does not trigger GPL distribution, but AGPL
  is not involved here; confirm with counsel before deciding a commercial model.
* Preserve ERPNext/Frappe copyright and licence notices; do not remove them from UI or files.
* Trademarks: ERPNext and Frappe names/logos belong to Frappe Technologies
  (`TRADEMARK_POLICY.md` in the archive). SERK Retail uses its own name and identity and must
  not present itself as ERPNext or as endorsed.
* Third-party dependency licences are not yet inventoried (SBOM is RET-SEC-010, planned).
