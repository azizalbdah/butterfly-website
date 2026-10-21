# Local staff development

Production remains on the saved website baseline. These commands operate only on
the `butterfly-staff-preview` development project and do not create a hosted
Supabase account, send real email, or publish a website.

The tested toolchain is Node 24, npm 11, Supabase CLI **2.121.0**, Docker,
Python 3.12 with `cryptography` **50.0.0**, Playwright **1.62.0**, and system
Chromium at `/usr/bin/chromium`. Staff dependencies are pinned by
`staff/package-lock.json`; install them with `npm --prefix staff ci`.
The cloud workspace's official CLI wrapper is
`/workspace/.butterfly-tools/supabase`. It sets a private `SUPABASE_HOME`, disables
telemetry, and selects the official slim images with
`SUPABASE_USE_SLIM_IMAGES=true`. The CLI can be installed independently with
`npm install --prefix /workspace/.butterfly-tools --no-save supabase@2.121.0`.
Keep tools, CLI state and generated credentials outside the public checkout.

```bash
cd /workspace/butterfly-website
python3 scripts/local-start.py
```

The helper verifies the project and CLI version, builds the actual invitation and publishing/media
handlers using the lockfile-pinned SDK, and starts the real Auth, Postgres,
Storage, Data API, Mailpit and Edge services. The self-contained local Edge
bundle avoids a certificate-chain failure in this environment's graph loader;
it does not disable TLS checks. The hosted source uses its pinned production
import map. Hosted deployment remains a separate acceptance step.

The helper preserves the owned containers' images, volumes, health probes,
network and HTTPS proxy while setting explicit empty HTTP proxies for internal
local HTTP. The Edge repair preserves the CLI-generated bootstrap before
recreating that one service. It never resets the database or prunes Docker.
An already running retained stack can use `--repair-only`. Use `--stop` to stop
only this development project while retaining its data volumes.

Private CLI work files, logs, signing material, local status, test credentials
and email captures live under `/workspace/.butterfly-private` with restricted
permissions. Do not print or commit their contents. The startup helper checks
real service responses and the actual function's anonymous rejection; a ready
message does not replace the authorization and invitation acceptance tests.

For the browser interface, put only `VITE_SUPABASE_URL` and
`VITE_SUPABASE_PUBLISHABLE_KEY` in ignored `staff/.env.local`, using the local API
URL and public anon/publishable key from private CLI status. Never use a
service-role or secret key. Then run:

```bash
npm --prefix staff run dev
```

The staff app is served at `/staff/` on loopback port 5173. Invitation/recovery
callbacks and the allowed function origin match that origin. Mailpit on local
port 54324 captures development mail; it does not verify hosted email delivery.
Use `npm --prefix staff run build` to build the static staff client. The chosen
host must enforce the security response headers documented in
[SUPABASE_SETUP.md](SUPABASE_SETUP.md).

Serve the public customer website with:

```bash
python3 scripts/serve-public.py --port 8000
```

Use this restricted server instead of a generic server at the checkout root:
backend setup files, environment files and Git metadata must not be public.
The staff Vite server also restricts filesystem access to the client and fonts.

The acceptance sequence is:

1. `python3 tests/backend_acceptance.py` — genuine local Auth/MFA, direct
   database and Storage permissions, invitation/reset email callbacks and
   session revocation/expiry. Creates disposable local fixture identities.
2. Capture and restore that fixture following
   [LOCAL_RECOVERY.md](LOCAL_RECOVERY.md), including `--runtime-api`. Keep source
   writes stopped throughout backup and rehearsal.
3. `python3 tests/staff_browser_acceptance.py` — genuine browser login,
   persistence/logout, MFA, invitations, password reset, Arabic/English, RTL
   and mobile behavior. Run after recovery because it changes fixture accounts.
4. `python3 -m unittest discover -s tests -p 'test_*.py'` and
   `python3 tests/browser_smoke.py --port 8000` — recovery safeguards and the
   public customer journey.

Do not reuse local fixture accounts or keys in production. No hosted project,
SMTP account, production backup schedule or off-site key custody is configured
by these commands.
