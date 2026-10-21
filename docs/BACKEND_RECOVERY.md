# Backend backup and recovery requirements

Updated on 21 October 2026. The encrypted **local development** backup and independent database/Auth/Storage API recovery rehearsal passed: 53 tables, 16 uploads, policy/function digests, captured extension dependencies, Auth/MFA/sessions, CRM assignment boundaries and booking prices, and actual published-photo/new-enquiry Edge requests after a clean 13-migration setup, with the source preserved. See [LOCAL_RECOVERY.md](LOCAL_RECOVERY.md). **No hosted project, production customer backup, off-site retention or scheduled production backup exists.** The requirements below govern that separate production setup.

Website code rollback and data recovery are separate operations. Reverting a website release must preserve enquiries, quotations, bookings, customers, activity, and uploads created after that release. **Never automatically restore an old production database when rolling back website code.** Follow the website baseline procedure in [ROLLBACK.md](../ROLLBACK.md); it does not substitute for the backend procedures below.

## Supabase plan capabilities

Official reference, checked for this preparation on 20 October 2026: [Supabase database backups](https://supabase.com/docs/guides/platform/backups). Confirm both the current vendor documentation and the selected project's dashboard before relying on a feature.

| Plan/feature | Documented capability | Consequence for this project |
| --- | --- | --- |
| Free | No automatic managed database backups and no PITR. | Schedule and verify private logical exports independently; do not assume a restore point exists. |
| Pro | Daily managed database backups with 7-day retention. | Confirm successful snapshots and recovery procedure in the actual project; separate uploaded-file backups remain necessary. |
| Team | Daily managed database backups with 14-day retention. | Confirm the project's enabled features and operator permissions. |
| Enterprise | Daily managed database backups with 30-day retention. | Confirm the project's contract and actual configuration. |
| Point-in-time recovery (PITR) | Paid add-on requiring at least Small compute; retention and pricing depend on the purchased configuration. | Do not assume PITR is included, enabled, affordable, or tested. Record the enabled window and restore evidence if selected. |

Managed database backups do **not** contain the uploaded object bytes stored by Supabase Storage. Database storage metadata is not a file backup. Restoring the database alone can leave missing or mismatched files. An account/project password or paid plan is also not evidence of a usable backup.

The owner must select and record a production recovery-point objective (maximum acceptable data loss) and recovery-time objective (acceptable downtime). Schedule export frequency and alerting to meet those objectives; a daily backup can lose the day's changes. Do not claim zero data loss without a tested mechanism that supports it.

## Separate recovery assets

Keep all private backups outside the public repository and public web root, encrypted with access limited to designated operators. Use a separate private backup destination with its own retention and recovery access. Never commit data dumps, Auth user exports, storage objects, signed URLs, passwords, tokens, or encryption keys.

Each backup set should have a non-sensitive manifest identifying:

- Environment/project reference, UTC capture time, application commit, migration version, and database/tool version.
- The database export and integrity checksum, consistent capture method, completion status, and any excluded schemas or data.
- Object inventory with bucket, object key/version where supported, size, capture time, and checksum; uploaded object bytes stored privately.
- A configuration inventory and links to secure records, rather than secret values.
- Known consistency boundaries, retention/deletion date, verification outcome, operator, and the matching restore-test evidence.

Capture and validate these components independently:

1. **Database:** application schemas/data, constraints, functions, RLS policies, grants, required extensions, migrations, audit records, price/version snapshots, and the supported Auth-related export needed for recovery. Ensure the backup tool actually includes required schemas; do not assume a generic dump includes Auth, roles, or Storage metadata. Use the provider's supported export/restore procedure for managed schemas.
2. **Uploaded files:** bytes from every relevant private/public bucket, plus inventories/checksums. Preserve customer-record relationships and published content versions. Document how new/changed/deleted objects are captured consistently with the database.
3. **Authentication configuration:** disabled public signup, enabled providers, verified Site URL/redirect allowlist, email templates/SMTP settings, MFA policy, session/token settings, and first-owner recovery procedure. Store provider credentials and recovery codes in a password manager, not this document. Verify what user credentials/MFA factors can be restored using supported tooling; do not assume sessions or password hashes are portable to a new project.
4. **Environment/server configuration:** project references, trusted origins, Edge Function versions/settings, secret **names**, Storage bucket policies/limits, scheduled jobs, email/DNS configuration, and monitoring destinations. Restore secret values securely from the designated credential store. Rotating project/signing credentials may invalidate sessions and require clients to sign in again.

Supabase database backups do not automatically recreate a deleted project's domain/DNS, external SMTP account, deployed frontend, all dashboard settings, or third-party integrations. Record the exact tested boundaries for the chosen restore path.

## Before every production migration

Do not run a production migration unless all of the following have current evidence:

1. The migration is versioned, reviewed, and tested against an isolated backend containing representative data. Use additive/backward-compatible changes where practical: add new columns/tables before depending on them, preserve old readers/writers during rollout, and delay removals to a separately reviewed release.
2. A successful, accessible database backup exists for the intended restore point, along with required file backups and Auth/environment configuration. Verify integrity and completeness, not just the existence of a filename or a scheduled-job configuration.
3. A compatible isolated recovery exercise has passed and the operator has the credentials/permissions needed for the documented restore path. If a new migration changes recovery assumptions, repeat the affected checks before production.
4. The release has an application rollback target, migration compatibility plan, maintenance/communication plan if needed, and a strategy to preserve writes received after the backup. Record exactly which failures would require a corrective migration versus data recovery.

If the backup is missing, incomplete, inaccessible, or untested, production migration remains blocked. Do not bypass this precondition by relying on an unverified paid feature or by inventing a successful backup checkpoint.

## Routine production backup workflow

1. Provision private, encrypted backup storage and an operator/job identity with the minimum necessary export access. Exclude the backup destination from public hosting and repository paths.
2. Use pinned, provider-supported database export tools with TLS and normal verification enabled. Retrieve credentials securely at execution time; avoid command-line passwords, shell tracing, credential-bearing URLs in logs, or secret values in reports.
3. Export the database and collect the matching file inventory/bytes with a documented consistency boundary. For a live site, record whether writes were briefly paused or how writes during capture are reconciled.
4. Check exit statuses, checksums, object counts/bytes, expected schemas and row counts, and current manifest timestamps. Upload the backup set to the private destination, verify it there, and alert on failure/staleness.
5. Enforce the approved retention policy. Test that an authorized operator can download and decrypt the backup without depending only on the production account being recovered.

The local-only commands in [LOCAL_RECOVERY.md](LOCAL_RECOVERY.md) have captured encrypted backups and passed an isolated SQL plus independent Auth/Storage API restoration. They deliberately cannot target a hosted project. A production command, scheduler, retention destination and cutover path still require the owner-controlled hosted project, selected plan and secure credential bindings. Local rehearsal is not evidence of a production backup or hosted recovery.

## Isolated recovery acceptance test

Use a separate temporary backend with no production traffic. Disable or redirect outbound email, webhooks, and other integrations before importing data. Never point a recovery rehearsal at the live database or reuse production frontend callback URLs blindly.

1. Record the selected backup set and target environment. Establish a clean target using the compatible Supabase/tool versions and supported restore procedure.
2. Restore required database schemas/data, role grants, functions, migrations, and policies. Restore uploaded bytes and reconcile them against Storage metadata and the checksum manifest.
3. Reapply Auth, Storage, Edge Function, email, origin, and environment configuration from the documented inventory; restore necessary secrets securely. Explicitly establish which users/passwords/MFA factors remain valid and which need a supported recovery/reset flow.
4. Check representative customers, linked enquiries, follow-up dates, audit history, catalogue/content versions, and immutable quotation/booking price snapshots. Compare row/object counts and all sampled checksums to the captured manifest.
5. Run direct API/RLS tests for anonymous, uninvited, inactive, Sales, Marketing, Admin `aal1`, and Admin `aal2`. Recheck assignment boundaries, self-escalation denial, private file access, invitation/reset paths, session expiry, and logout. Do not send real customer messages.
6. Exercise the restored application against the restored backend, including Arabic/English, publishing/version boundaries, and pricing. Measure recovery duration and the newest recoverable record; compare them with the agreed objectives.
7. Record the source manifest identifier, commands/tool versions, sanitized results, failures, operator, and tested commit. Keep private evidence outside the public repository. Tear down or secure the isolated environment according to the approved retention plan.

Passing a database import alone does not pass recovery. A test that omits object bytes, Auth configuration, permission checks, or post-backup writes must state those limitations.

## Production recovery decision

Prefer rolling back only the frontend or applying a corrective forward migration when that preserves valid records. If corruption or destructive changes require data recovery, stop and plan the operation with the owner: retain the current database and file state, identify the affected time range, reconcile records received after the restore point, validate an isolated recovered copy, and perform an explicitly authorized cutover.

Do not overwrite the live backend as a routine website rollback step. Keep the unrecovered/current state until reconciliation is complete. After a real cutover, verify application/API access, new submissions, file access, Auth redirects, and notification behavior; record the recovery checkpoint and any actual data loss honestly.
