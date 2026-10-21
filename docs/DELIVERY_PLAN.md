# Staff dashboard delivery gates

Status on 21 October 2026: **Stages A, B and C passed their local acceptance gates; Stage D implementation and browser acceptance are complete; final recovery/checkpoint verification is in progress.** Production remains on the preserved website baseline. Stage B is a genuine local backend and browser checkpoint, not a verified hosted deployment. See [the sanitized Stage B report](checkpoints/stage-b-local-2026-10-21.json).

## A — Baseline and preview

Completed: rechecked local and remote main at `ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd`; preserved baseline tag and backup branch locally and on origin; verified an independent archive and Git-bundle restoration; served the archive in a separate preview and passed all 13 browser smoke groups. See [ROLLBACK.md](../ROLLBACK.md).

Production gate passed: GitHub Pages legacy `main:/`, custom domain `butterflykwt.com`, HTTPS enforced, successful build `1284897299` and deployment `7074909245` both at the baseline SHA. All five representative production file hashes match. The real API/HTTPS verifier and its adversarial tests pass. A locally running preview is not a hosted staging deployment; no feature code has been published to production.

## B — Authentication and permissions

The local Supabase stack is running and the staff access migration has been applied locally. Implemented backend controls include invitation-only authentication, active staff membership, session-bound Admin/Sales/Marketing roles, mandatory administrator MFA, immutable audit events and private media permissions. The separate staff interface implements login, password recovery, session handling, administrator MFA and staff management, and passed all 13 real browser acceptance groups.

All **15 backend acceptance groups passed**, including real invitation email delivery and password setup, reset, refresh/logout, expiry, MFA revocation and private-media boundaries. The invitation runtime routing issue is resolved. The isolated encrypted backup/recovery rehearsal passed for 40 tables and three uploads, including a separate Auth/Storage/Data API runtime with recovered sessions, MFA, role permissions and exact file bytes. Source data was preserved. All 26 unit tests, all 13 public browser groups and the staff production build passed. The local startup helper also passed a repeated repair/readiness run. See [LOCAL_PREVIEW.md](LOCAL_PREVIEW.md) and [LOCAL_RECOVERY.md](LOCAL_RECOVERY.md).

No hosted Supabase project, production SMTP service or hosted staff preview has been provisioned. [SUPABASE_SETUP.md](SUPABASE_SETUP.md) describes configuration and [BACKEND_RECOVERY.md](BACKEND_RECOVERY.md) describes the separate recovery requirements. `.env.example` contains public placeholders only. Development fixtures and credentials remain private and outside public previews.

Acceptance: real Supabase connection; invitation-only login, reset, logout, refresh/persistence and expired/revoked session handling; mandatory administrator MFA; database-enforced Admin/Sales/Marketing roles; no self-escalation; audit events; private uploads. Test direct REST/database/Storage access for anonymous, uninvited, inactive, wrong-role, wrong-assignee and administrator aal1/aal2 cases. Test an isolated backup/recovery before claiming recoverability. Build the private staff UI separately from public tracking. Commit and tag a tested B checkpoint only after this passes.

## C — Content and package publishing

Completed locally: 472 imported bilingual/text/image/link/SEO fields; private Marketing drafts; MFA-admin package editing and publishing; safe real-page previews; concurrent-edit rejection; immutable revisions and paginated history; private staged photos served publicly only after successful publication. The same published catalogue and shared pricing engine drive the public calculator and staff preview. See [PUBLISHING.md](PUBLISHING.md) and [the sanitized Stage C report](checkpoints/stage-c-local-2026-10-21.json).

Acceptance passed: 55,494 comparisons against the saved calculator, eight direct publishing API groups, eight real publishing browser groups, 15 backend security regression groups, 13 staff-auth browser groups, 13 public browser groups and 29 unit tests. A clean official Supabase project applied all six captured migrations, then restored and checked 45 tables, 12 uploads, Auth/MFA/sessions, permissions and published content/catalogue/media visibility. The source was preserved. Backup `stage-c-003` captured clean application commit `9f1d5da2f6414f3273af61e7d5c2ebc035276210`; private artifacts and keys are outside the repository. Hosted setup remains pending.

Only begin after B passes. Import existing AR/EN content and approved package data. Preserve the logo font and quiet luxury design. Add explicit draft/preview/publish/version-history states and publish atomically with auditing; permit Marketing drafts and media, and Admin prices/publishing. Store one authoritative published package catalogue used by the dashboard and public calculator. Preserve the current recommendation rules, guest capacities, prices and add-ons, testing old versus new results across capacities, extensions, hours, towers, unavailable packages and custom quotations. Snapshots must retain the catalogue version and calculated price used by each enquiry/quotation. Test persistence, concurrent editing, invalid publishes, anonymous published reads, private draft isolation, AR/EN, RTL/mobile and keyboard access. Commit/tag only after acceptance passes.

## D — Enquiries, customers and follow-ups

Only begin after C passes. Add real overview counts and date filters with empty states; board/table pipeline (New, Contacted, Quotation Sent, Confirmed, Completed, Lost); assignment, next action, follow-up date, notes and loss reason; related customer/company records and history. Use validated anonymous submissions through a rate-limited server function with server-calculated price snapshots. Separate submission, WhatsApp opening, quotation sending and booking confirmation. A client opening WhatsApp is not evidence that a message was sent. Enforce assignee permissions at the database. Check customer matching without merging unrelated records, activity/audit consistency, overdue follow-ups and date boundaries. Test later records survive website rollback.

Maintain Foodics, Ordable and Respond.io in their existing roles; no integration is currently connected or tested. Preserve external ordering links and public tracking, and keep marketing pixels off staff screens. The public customer journey must not require login.

## Release and later scope

Production stays on the stable release until all applicable acceptance checks pass in a separate preview deployment. A production migration requires a current verified backup and recovery evidence; do not use a UI success message or local test fixture as proof. Keep small commits and fresh, clearly named tested checkpoints after each completed stage. Never force-push `main` as normal recovery.

Quotation templates/PDF generation, event scheduling and a customer portal belong to a later release. Define their permissions, snapshot semantics and recovery requirements before adding them to initial delivery.
