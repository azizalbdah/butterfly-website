# Supabase setup and staff security

Updated on 21 October 2026. Stage A passed. A genuine local Supabase stack now runs the versioned staff access migration and separate staff client. All 15 direct-backend acceptance groups and the isolated database/Auth/Storage API recovery rehearsal passed locally. Check [DELIVERY_PLAN.md](DELIVERY_PLAN.md) for the complete stage gate and browser acceptance status. No hosted Supabase project or staff deployment has been created.

The public website remains static HTML, CSS and JavaScript. The private staff client has its own pinned Vite build under `staff/` and connects to real Supabase Auth/Postgres/Storage. Public ordering links and tracking remain in their existing roles. Foodics, Ordable and Respond.io have not been connected or tested by this work. See [LOCAL_PREVIEW.md](LOCAL_PREVIEW.md) for the tested local workflow.

## Architecture

- Keep the public website usable without a customer account. Build the private staff interface separately, using Butterfly's existing logo font, bilingual content, RTL support, and keyboard/mobile navigation.
- Use Supabase Auth for invitation-only staff access, Postgres for records and versioned content, private Storage for protected uploads, and server-side Edge Functions for privileged actions and validated public submissions.
- Staff dependencies are pinned in `staff/package-lock.json`. The staff access schema is versioned under `supabase/migrations/`; the invitation Edge Function is under `supabase/functions/invite-staff/`. Apply changes in preview before production. Use backward-compatible migrations and preserve newer records during website rollback.
- Enforce Owner/Admin, Sales, and Marketing access in database policies and server functions. Owner/Admin can manage users, permissions, prices, publishing, and all records; Sales can access assigned records and follow-ups; Marketing can prepare content drafts and media. UI controls supplement these policies.
- Store active staff membership and roles in a protected database table. Do not derive authorization from editable user metadata, let users change their own role, or automatically promote the first person who signs up.
- Require a verified administrator MFA session (`aal2`) for administrator data and privileged operations. A minimally scoped own-profile query can identify the role before MFA, without exposing customer records or administrator capabilities. Handle enrollment, challenge, recovery, session expiry, token refresh, password reset, and logout as acceptance checks.
- Keep service-role and database credentials server-side. Privileged invitation and user-management functions must verify the caller's authenticated, active administrator membership and MFA before using privileged credentials.
- Keep marketing pixels and external tracking out of all private staff screens. Use designated editable fields and safe text/URL rendering instead of accepting arbitrary executable HTML.

## External setup the owner must complete

1. Create an organization in a user-owned Supabase account at <https://supabase.com/dashboard>. Protect the Supabase account with MFA and retain recovery access outside this repository.
2. Create a dedicated **preview** project, for example `butterfly-preview`. Select and record its region and plan. Use a unique database password stored in the organization's password manager. Do not send passwords or keys in chat.
3. Record the project reference and API URL. Select the project's **publishable** browser key. A legacy `anon` key is also public client configuration, but is not a privileged server key. Security must come from RLS and validated server functions rather than secrecy of a browser key.
4. Prepare secure environment bindings in the chosen preview host and server platform. Do not commit actual values. The deployment host and final callback URLs are not yet verified; do not assume GitHub Pages can run Edge Functions or a Node server. Supabase Edge Functions run on Supabase; GitHub Pages can only serve static client files.
5. In the preview project's Auth configuration, enable the intended email/password workflow and **disable new public signups**. Staff invitations will be created by an authorized administrator. Disable unused providers.
6. After the preview origin is verified, set Auth's Site URL and an explicit redirect allowlist for the staff application's implemented invitation and password-recovery callback. Avoid broad production wildcards. Do not use a production origin for preview recovery links. Callback paths will be recorded and exercised when the Stage B client exists.
7. Configure a verified sending domain and production-capable SMTP/email provider for staff invitations and resets. Keep its credentials in the provider's secure settings. Supabase's restricted/default email service must not be assumed suitable for a production staff rollout. Confirm delivery, allowed recipients, rate limits, and invitation/reset expiry in preview.
8. Enable the intended TOTP MFA capability. After the migrations and invitation path exist, invite the first owner using a controlled server-side/bootstrap procedure, assign their role through a privileged operation, and complete MFA enrollment before opening administrator access. Never implement a public first-user-admin route.
9. Create a separate **production** project only when the stage acceptance checks pass. Use separate credentials, users, storage, backups, email configuration, and exact production redirects. Review the selected plan, costs, and the backup requirements in [BACKEND_RECOVERY.md](BACKEND_RECOVERY.md) before importing live records.

No secret values are needed in chat. Supply credentials only through the Supabase dashboard, a password manager, or secure deployment/environment settings. Do not put them in GitHub Pages files, workflow logs, screenshots, commits, or a public `.env` file.

## Environment configuration

The root and staff `.env.example` files contain names and placeholders only. Actual private bindings stay outside the public checkout; `staff/.env.local` contains only public browser configuration and is ignored by Git.

| Binding | Scope | Purpose |
| --- | --- | --- |
| `VITE_SUPABASE_URL` | Public staff build configuration | Project API URL for the selected environment. |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Public staff build configuration | Browser API access subject to RLS; never a service-role key. |
| `SUPABASE_URL` and `SUPABASE_ANON_KEY` | Server/Edge Function runtime | Supabase-provided project URL and public key used to validate caller identity and invoke policies with the caller JWT. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server/Edge Function runtime only | Privileged Auth operations after caller authorization; reuse the platform-provided binding when applicable. Never bundle it into browser code. |
| `SUPABASE_ACCESS_TOKEN` | Private operator/CI deployment environment only | Supabase CLI management/deployment, if required; not an application browser credential. |
| `SUPABASE_DB_PASSWORD` or a private database connection binding | Private operator/CI environment only | Approved migrations and backup operations. Do not embed a connection URL containing a password in shell history or documentation. |
| SMTP provider settings | Supabase Auth/provider settings | Invitation/reset delivery; keep credentials in secure settings. |
| `BUTTERFLY_STAFF_ORIGIN` and `BUTTERFLY_STAFF_REDIRECT_URL` | Edge Function runtime, non-secret | Exact permitted staff origin and `/staff/` invitation callback; mandatory for the invitation function. |
| Verified staff origins and callback URLs | Non-secret per-environment configuration | Explicit invitation/reset destinations, CORS checks, and preview/production separation. |

Never duplicate existing secure bindings without checking their names and operation first. A publishable key is not evidence that invitation administration, database backups, or deployment permissions work.

The staff client uses a separate Vite build under `staff/`; it never needs the service-role key. Vite rejects privileged keys in public configuration before creating the bundle. The local preview/dev host sets CSP including `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `X-Content-Type-Options: nosniff`. The eventual staff host must enforce those response headers. Legacy GitHub Pages cannot supply arbitrary response headers, so its public-site configuration must not be treated as a verified secure staff-host deployment. The production staff host is not selected or deployed yet.

## Recurring services and plan decisions

The initial hosted workflow needs Supabase database/Auth/Storage, staff/public static hosting, email delivery, an owned domain/DNS, and an external private backup destination plus a scheduled backup job. Optional CAPTCHA/abuse protection for anonymous public submissions may add a provider. Existing Foodics, Ordable, and Respond.io services remain separate; this plan does not replace them or claim an integration.

Record the selected Supabase plan, compute size, region, quotas, usage alerts, billing owner, backup schedule/retention, and email limits before production. Database size, Storage bytes/egress, monthly active users, Edge Function usage, email volume, and backup storage can incur recurring charges. No paid feature is assumed enabled. Current vendor pricing and the actual account configuration must be checked before purchase or launch.

## Stage B acceptance gate

Stage B is complete only after a real preview project or genuine local Supabase stack is connected and these checks pass. A local HTML login, mocked metrics, or a successful dependency installation does not satisfy the gate.

1. Apply versioned migrations to an isolated backend and prove they are repeatable from a clean database. Enable RLS on every exposed customer/staff table; restrict function grants and use fixed, safe `search_path` values for privileged database functions.
2. Test invited login, uninvited/public-signup rejection, reset delivery/callback, logout, expiry, refresh, persistence, disabled membership, and administrator MFA enrollment/challenge.
3. Make direct REST/database/Storage requests as anonymous, uninvited, Sales, Marketing, Admin at `aal1`, and Admin at `aal2`. Check assigned-record boundaries, cross-customer denial, self-role-escalation denial, unauthorized publishing/pricing denial, and private-object denial. Hiding a button is not a permission test.
4. Confirm that privileged keys never appear in browser bundles/network responses and that private screens do not load public marketing pixels.
5. Create a real private backup and complete an isolated database, Auth-configuration, and file recovery exercise described in [BACKEND_RECOVERY.md](BACKEND_RECOVERY.md). Record evidence and limitations without exposing customer data or secrets.
6. Recheck that the unchanged public customer journey still works without login. Record the tested commit and recovery checkpoint before proceeding to Stage C.

Only after Stage B passes should Stage C implement safe versioned content/package publishing and then Stage D implement enquiries, customers, and follow-ups. Future quotation PDFs/templates, event scheduling, and a customer portal are outside the initial release.
