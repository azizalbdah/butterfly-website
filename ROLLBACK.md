# Butterfly website baseline and rollback

Recorded 20 October 2026. **Stage A passed: production baseline, hosting settings, and isolated local recovery are verified.** No production deployment, production setting, or database has been changed. Development continues on the separate feature branch.

## Preserved source

| Item | Value |
| --- | --- |
| Repository | `azizalbdah/butterfly-website` |
| Rechecked local HEAD and remote `main` | `ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd` |
| Annotated baseline tag | `baseline/butterfly-pre-staff-2026-10-20-ad8cda0` |
| Backup branch | `backup/butterfly-pre-staff-2026-10-20-ad8cda0` |
| Development branch | `feature/butterfly-staff-dashboard-2026-10-20` |
| Pre-existing working changes | None; tracked and untracked status was clean before edits |

The baseline tag and backup branch were pushed to `origin` successfully. Neither existing checkpoints nor `main` were overwritten. The feature branch contains preparatory work, not a release. Checkpoints created later must use new names; never move the baseline tag or force-push recovery refs.

A complete Git bundle is also stored **outside the public checkout**:

`/workspace/backups/butterfly-pre-staff-2026-10-20/baseline-ad8cda0.bundle`

SHA256: `98d835790893bc02ccb50ecf5746e4ac3fff99235a300f64047d8dd225b086e8`.

`git bundle verify`, cloning that bundle to a separate directory, `git fsck --full`, and resolving the saved tag and restored HEAD all passed. This is a website-source backup; it contains no customer database or uploaded files. Copy private backup artifacts to an owner-controlled backup location before depending on this workspace for disaster recovery.

## Accepted local dashboard checkpoints

| Stage | Git tag | Backend recovery evidence |
| --- | --- | --- |
| A | `checkpoint/butterfly-stage-a-2026-10-20` | Verified public archive and offline Git-bundle restoration. |
| B | `checkpoint/butterfly-stage-b-local-2026-10-21` | 40-table, three-upload isolated Auth/Storage recovery. |
| C | `checkpoint/butterfly-stage-c-local-2026-10-21` | Clean six-migration setup and 45-table, 12-upload isolated recovery; published state, Auth, MFA and permissions checked. |

These are local acceptance checkpoints, not hosted production releases. The
original website baseline remains the website rollback target. The latest private
backend rehearsal is `stage-c-003`; restore it only into a fresh isolated target
following [LOCAL_RECOVERY.md](docs/LOCAL_RECOVERY.md). It is not a production
customer backup. The code/report checkpoint does not authorize restoring an old
database over newer records. Production was reverified unchanged on 21 October
2026; see [the sanitized report](docs/checkpoints/production-baseline-2026-10-21.json).

## Deployment configuration: confirmed versus unknown

Confirmed from the preserved tree:

- `CNAME` contains **`butterflykwt.com`**. Keep this file and domain unchanged during a public website rollback.
- The site is four static HTML pages, local JavaScript, images and fonts. There is no package manifest, dependency installation, framework build, or tracked CI/deployment workflow. The source tree itself is the static output. The file `test` is legacy HTML, not a test runner.
- The public calculator is `assets/catering-configurator.js`; the baseline preserves its approved rules, prices and recommendation behavior.

Verified from the actual GitHub API and production site at 13:22 UTC (16:22 Kuwait time) on 20 October 2026:

- Hosting is public GitHub Pages, **legacy branch build from `main`, directory `/`**, with status `built`.
- The configured custom domain is `butterflykwt.com`, and HTTPS enforcement is enabled. All five representative HTTPS requests stayed on that domain; no TLS verification was disabled. DNS zone records were not changed or independently audited.
- Latest successful Pages build: **1284897299**, created `2026-10-14T19:17:13Z`, completed `2026-10-14T19:18:24Z`.
- Latest active successful `github-pages` deployment: **7074909245**, success recorded `2026-10-14T19:18:35Z`.
- Both build and deployment identify the saved baseline SHA. The four public HTML pages and calculator JavaScript match their saved Git blobs byte for byte (SHA256).

The initial requests were blocked by network policy. After adding `api.github.com` and `butterflykwt.com` while preserving existing domains, actual requests succeeded. Sanitized evidence is committed in [production-baseline-2026-10-20.json](docs/checkpoints/production-baseline-2026-10-20.json). Repeat the read-only check with:

```bash
cd /workspace/butterfly-website
python3 scripts/verify-production-baseline.py --output /tmp/butterfly-production-verification.json
```

The verifier fails if deployment identity, source settings, expected custom domain or public file fingerprints cannot be established. Once a later release is intentionally deployed, a baseline mismatch is expected and must not be relabeled a passing baseline check. Existing HTTPS Git/API authentication works; never paste a token into chat. The actual redeployment path is a reviewed recovery commit merged to `main`, which GitHub Pages builds from the repository root. Keep Pages source settings and DNS unchanged.

## Tested isolated restoration

The saved commit was exported, with no Git metadata or working-copy dependencies, to `/tmp/butterfly-baseline-preview`. All **27 files** matched the original Git blobs. The archive SHA256 is:

`507d98e28236f8f302861c046967d8e55493aee6b97cbd57fc5d2722d8c1e337`

The recovered site was served on loopback port 8001. Five HTTP/content checks and 13 Chromium smoke-check groups passed: all four pages, decoded images, Arabic/English and language persistence, mobile menus, keyboard wizard focus, coffee 125 KD, hospitality 475 KD, a 22 KD add-on yielding 497 KD, guest validation, custom quotations and corporate enquiry draft generation. `window.open` was intercepted; no WhatsApp messages were sent. No uncaught JavaScript errors occurred. Eight missing image variants use their working baseline fallbacks.

Evidence on this machine:

- `/tmp/butterfly-baseline-recovery-report.json`
- `/tmp/butterfly-baseline-browser-report.json`
- `/tmp/butterfly-baseline-http.log`
- `/workspace/backups/butterfly-pre-staff-2026-10-20/public-export-manifest.json`

Create another verified export without touching the active checkout (choose a fresh destination; existing files are refused):

```bash
cd /workspace/butterfly-website
python3 scripts/export-baseline.py --destination /tmp/butterfly-baseline-restored
python3 -m http.server 8002 --bind 127.0.0.1 --directory /tmp/butterfly-baseline-restored
```

Run internal HTTP/content and browser checks against that port. There is no build command. Ports and processes are local validation only, not a hosted preview or evidence of a production redeploy. No online preview has been deployed.

The reusable browser test runs with the installed Python Playwright and `/usr/bin/chromium`:

```bash
python3 tests/browser_smoke.py --port 8001
```

To recover source after loss of this checkout:

```bash
git clone --branch backup/butterfly-pre-staff-2026-10-20-ad8cda0 https://github.com/azizalbdah/butterfly-website.git /tmp/butterfly-source-recovery
git -C /tmp/butterfly-source-recovery rev-parse HEAD
git -C /tmp/butterfly-source-recovery rev-parse 'refs/tags/baseline/butterfly-pre-staff-2026-10-20-ad8cda0^{commit}'
```

Both hashes must equal the recorded SHA. If GitHub is unavailable, the tested offline alternative is:

```bash
git clone --branch backup/butterfly-pre-staff-2026-10-20-ad8cda0 /workspace/backups/butterfly-pre-staff-2026-10-20/baseline-ad8cda0.bundle /tmp/butterfly-offline-recovery
git -C /tmp/butterfly-offline-recovery fsck --full
git -C /tmp/butterfly-offline-recovery rev-parse HEAD
```

## Production recovery procedure

1. Identify the incident and pause new publishing. Preserve the current production deployment identifier and all customer data. Confirm the target tag resolves to the recorded SHA and run the isolated export/preview checks above.
2. Use the **verified host's** redeploy-existing-release action for that SHA, or deploy the verified static export as a new release. Keep the configured custom domain, HTTPS and ordering links. Do not repoint DNS or rewrite `main` to perform normal recovery.
3. If a source-branch deployment requires a new commit, create a recovery branch from the current `origin/main`, restore only public website files from the baseline, review a PR and merge normally. Preserve all versioned database migrations, recovery documentation and server-side configuration. Remove any later staff client from the deployment artifact if restoring the original website. Never blindly reset the whole repository to the old commit.
4. The known baseline public paths are `CNAME`, `assets/`, `business.html`, `catering.html`, `favicon.ico`, `fonts/`, `images/`, `index.html`, `links.html` and `test`. A website-only restore in a clean recovery branch can start with:

   ```bash
   git fetch origin
   git switch -c recovery/butterfly-public-baseline origin/main
   git restore --source=baseline/butterfly-pre-staff-2026-10-20-ad8cda0 --staged --worktree -- CNAME assets business.html catering.html favicon.ico fonts images index.html links.html test
   git diff --cached --stat
   ```

   Inspect and test before committing. If future public files exist outside those paths, exclude them from the rollback deployment artifact; do not delete database migrations to obtain an old website tree. Use a fresh recovery branch name if the example already exists. Do not run this procedure over uncommitted work; preserve that work first.
5. After deployment, verify deployment status/SHA and custom-domain HTTPS; exercise all public pages, language controls, image fallbacks, calculator prices and enquiry submission against the still-current backend. Keep new enquiries/bookings available even if the old website no longer displays their capture interface.
6. Merge the reviewed website recovery commit to `main` normally. If an explicit rebuild of that already-restored `main` is needed, the verified legacy Pages API supports `gh api --method POST repos/azizalbdah/butterfly-website/pages/builds`. This is a production action: do not run it during preview testing. Check `gh api repos/azizalbdah/butterfly-website/pages/builds/latest` and the actual deployment statuses until successful, then repeat the public checks. A recovery commit has a new SHA; verify its public files against the baseline rather than expecting its deployment SHA to equal the old tag.
7. Record the recovery release and evidence. This work tested isolated recovery and inspected the real successful baseline deployment; it did not perform a production redeploy.

**A website rollback must never automatically restore an old database.** Records and uploads created after launch must survive it. Database, file, Auth and environment recovery are separate incident procedures in [BACKEND_RECOVERY.md](docs/BACKEND_RECOVERY.md). The separate staff backend now has versioned migrations and a tested local encrypted recovery workflow in [LOCAL_RECOVERY.md](docs/LOCAL_RECOVERY.md). No hosted production backend or production customer backup has been configured. Preserve all later backend migrations and records when restoring the website.
