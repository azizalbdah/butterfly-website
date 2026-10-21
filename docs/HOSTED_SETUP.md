# Owner-controlled hosted setup

These are external prerequisites. No hosted Supabase project, SMTP provider or
staff/public preview host has been created by the local acceptance tests. Do not
send passwords, access tokens or privileged keys in chat. Keep production on the
saved release until the hosted preview passes acceptance.

## Preview project and authentication

1. Create the Supabase organization and a new empty preview project in the owner's
   account. Enable account MFA, save recovery access in the owner's password
   manager, and record the project reference, region, Postgres version and plan.
   Choose a separate production project later. Review
   [BACKEND_RECOVERY.md](BACKEND_RECOVERY.md); no paid backups or PITR are assumed.
2. Choose a separate HTTPS staff preview host that can enforce response headers.
   Its application path is `/staff/`. Record the exact origin, for example
   `https://YOUR_STAFF_PREVIEW_HOST`, and callback
   `https://YOUR_STAFF_PREVIEW_HOST/staff/`. Legacy GitHub Pages alone cannot
   supply the required staff security headers.
3. In Supabase Auth, keep email/password available, disable public signup and
   anonymous users, enable TOTP MFA, and disable unused providers. Set Site URL
   and the explicit redirect allowlist to the staff callback. Avoid broad
   wildcards. Retain the tested password policy and short access-token lifetime
   from `supabase/config.toml`; verify hosted Auth settings independently.
4. Configure an owner-controlled SMTP provider with a verified sending domain,
   sender address and DNS records. Store its credentials only in secure provider
   settings. The local Mailpit sink does not prove hosted mail delivery.
5. Authenticate the official Supabase CLI through its supported secure login.
   From this checkout, set the non-secret project reference in
   `BUTTERFLY_PROJECT_REF`, link **preview**, and inspect migrations before
   applying them:

   ```bash
   supabase link --project-ref "$BUTTERFLY_PROJECT_REF"
   supabase db push --linked --dry-run
   supabase db push --linked
   ```

   Apply the complete tested migration set before inviting accounts or enabling
   application traffic. These are documented commands, not proof they have run
   against a hosted project. For an existing backend, take a verified current
   backup and plan the upgrade before applying migrations; never reset it to
   obtain an empty database. Do not use the generated private local runtime
   workdir for hosted deployment.
6. In an owner-private file outside the checkout, set the non-secret
   `BUTTERFLY_STAFF_ORIGIN` and `BUTTERFLY_STAFF_REDIRECT_URL` to those exact HTTPS
   values. Include `BUTTERFLY_PUBLIC_ORIGINS` as a comma-separated list of exact
   approved public preview HTTPS origins, without paths or wildcards. Generate
   `BUTTERFLY_ENQUIRY_RATE_SECRET` with at least 32 random bytes into that private
   file (for example using Python's `secrets.token_urlsafe(48)`, writing directly
   to the protected file). It stays server-only; do not print or paste it in chat.
   Bind that file with `supabase secrets set --env-file PRIVATE_FILE
   --project-ref "$BUTTERFLY_PROJECT_REF"`. Supabase supplies the server project
   URL, anon key and service-role key to functions; do not copy the privileged key
   into the staff build or public website. Deploy the implemented functions from
   this source checkout:

   ```bash
   supabase functions deploy invite-staff --project-ref "$BUTTERFLY_PROJECT_REF"
   supabase functions deploy publish-site --project-ref "$BUTTERFLY_PROJECT_REF"
   supabase functions deploy site-media --project-ref "$BUTTERFLY_PROJECT_REF"
   supabase functions deploy submit-enquiry --project-ref "$BUTTERFLY_PROJECT_REF"
   ```

   The source configuration uses pinned production import maps. Local bundles
   avoid this cloud development runtime's graph-loader certificate issue; no TLS
   verification was disabled. Hosted compilation and function delivery must pass
   in the actual preview project before claiming deployment works.

## Staff build, first owner and hosted verification

1. Set only `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` in the private
   build settings or ignored `staff/.env.local`. Use the preview project's public
   publishable/anon key. Build with `npm --prefix staff ci` followed by
   `npm --prefix staff run build`. Privileged browser keys are rejected during
   configuration validation. Create the curated release with
   `python3 scripts/build-staff-release.py --destination FRESH_RELEASE_DIRECTORY`.
2. The release contains the built client under `/staff/`, response-header rules
   in root `_headers`, and a root redirect in `_redirects`. The rules use the
   Netlify/Cloudflare Pages format; use a host supporting these files or translate
   the exact rules to its supported configuration. Deploy only that
   curated artifact, never the repository root or private work directories.
3. Enforce these response headers on `/staff/*`: `X-Frame-Options: DENY`,
   `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, and CSP matching
   the tested `staff/vite.config.js` policy, including `frame-ancestors 'none'`.
   Use the exact preview project origin for API/image connections, not a
   wildcard. The CSP must permit the editor's local blob styles/images and
   script-free preview frame. Check real response headers after deployment;
   a meta tag alone does not enforce `frame-ancestors`.
4. Bootstrap only the first owner through the trusted Supabase dashboard/operator
   path: invite the intended owner in Auth after SMTP and redirects are configured,
   obtain that invited Auth user's UUID, then use the SQL editor to insert that
   exact user into `public.staff_members` with role `admin`, `active=true` and the
   approved display name. Do not assign by editable Auth metadata, allow signup,
   promote the first login, or expose a bootstrap route. Complete password setup
   and authenticator enrollment before accessing administrator features.
5. Use the MFA-gated staff invitation UI for subsequent colleagues. Verify real
   invite/reset delivery to intended owner-controlled recipients; exact callbacks;
   login, refresh, expiry and logout; disabled memberships; Admin MFA; Sales and
   Marketing denial cases; private originals/staged photos; publishing and public
   media. Test through direct APIs as well as the browser. Recheck that no
   privileged key appears in deployed assets and no marketing pixels run on
   staff screens. The local acceptance scripts intentionally refuse hosted URLs;
   hosted test identities and checks need an explicitly controlled preview run.

## Public preview and production gate

Create a private public-only JSON configuration with `supabaseUrl` and
`publishableKey` for preview, then export the public site with
`scripts/build-public-preview.py --credentials PRIVATE_PUBLIC_CONFIG
--destination FRESH_EXPORT_DIRECTORY`. Deploy that export to a separate HTTPS
preview host. It contains no production CNAME, staff files, backend source or
privileged key. Verify the real published content/catalogue, photo endpoint,
languages/RTL, calculator rules, outage behavior, keyboard/mobile journey,
ordering links and public tracking. Check actual anonymous catering/corporate
capture, receipts and safe retries; distinguish saving from the optional
WhatsApp step; verify assignment isolation, quotation/booking actions and frozen
prices. The staff overview must reflect these real preview records. See
[CRM.md](CRM.md) for workflow and date-filter semantics.

Before production: select and record the plan and usage costs; configure verified
database/Auth/Storage backups, external retention and separate key custody;
rehearse hosted recovery and preserve later writes; finish the applicable stage
acceptance in hosted preview; configure separate production credentials, domains,
SMTP, exact callbacks and response headers. Record the successful production
deployment/configuration after release. No automatic website rollback may restore
an older database or delete newer uploads, enquiries or bookings.
