# Local preview backup and isolated recovery

These tools are limited to the real **local** `butterfly-staff-preview` Supabase stack. They cannot target a hosted project or restore over the source database. They do not configure production backups, paid recovery features, a backup schedule, or external retention. See [BACKEND_RECOVERY.md](BACKEND_RECOVERY.md) for the separate production prerequisites.

The scripts require Python 3 with `cryptography`, Docker access to the local database container, and the private local Supabase state file. They preserve normal verification and use AES-256-GCM authenticated encryption. The encryption key is a separate private file outside the backup set. Private backups, decrypted recovery evidence and keys must stay outside the served checkout. Copy approved backups and their separately protected keys to owner-controlled storage before relying on them for disaster recovery.

Database operations use the local container's trusted `supabase_admin` operator over its local socket. This is necessary to preserve managed-schema ownership, grants and extension definitions; it is never a browser credential or a hosted recovery path. The scripts never replay global-role changes into the source cluster.

Stop local application writes and finish the backend acceptance fixture before capture. Choose new names for every run; existing destinations and keys are never overwritten:

```bash
cd /workspace/butterfly-website
python3 scripts/local-backup.py \
  --destination /workspace/.butterfly-private/backups/stage-d-001 \
  --key-file /workspace/.butterfly-private/backup-keys/stage-d-001.key \
  --fixtures /workspace/.butterfly-private/crm-fixtures.json
python3 scripts/local-recovery-check.py \
  --backup-set /workspace/.butterfly-private/backups/stage-d-001 \
  --key-file /workspace/.butterfly-private/backup-keys/stage-d-001.key \
  --destination /workspace/.butterfly-private/recovery/stage-d-001 \
  --runtime-api
```

The backup includes a custom-format dump of application/Auth/Storage/migration schemas, an encrypted global-role export, actual uploaded object bytes downloaded through the local Storage API, the versioned Storage volume archive, a schema/data checksum inventory, local Auth configuration and signing-key bindings, migration filenames/hashes and encrypted migration sources, and the verified self-contained Edge handler bundles plus private server bindings. Handler/source/shared-pricing/lockfile hashes must match before capture. When `--fixtures` is supplied, matching local test identities are captured inside encryption too; recovery uses that captured fixture automatically. This keeps password changes from later browser tests from invalidating a repeated rehearsal. Decrypted test fixtures remain only in the private recovery directory. The public manifest records credential **names only**; actual Auth private JWKs and legacy signing material are inside authenticated encrypted artifacts. Database dumps, role exports, runtime bindings and file bytes are encrypted before being written. Private file modes are `0600` and new private directories use `0700`. Do not place the real local state or encryption keys in `.env` inside the static web root.

The local capture compares table, policy and object-metadata digests before and after copying. It rejects a changing source; it does not claim an atomic distributed snapshot or live-production write reconciliation. Keep local writes stopped throughout backup and rehearsal. A failed or partial set without a completed manifest is not a usable backup.

The rehearsal verifies encrypted/plaintext checksums before creating a new internally named `butterfly_recovery_*` database in the local PostgreSQL container. It restores there, compares every captured table digest/count and RLS/function definition digest, restores object bytes into a private recovery directory, checks those bytes against the restored Storage metadata, and can test restored staff role boundaries using the acceptance fixture. The disposable database is removed after the check; the source `postgres` database is never a restore destination. The private report records the result and limits.

With `--runtime-api`, the rehearsal additionally starts a freshly named local Supabase project using the official CLI and cached slim images. It first applies the captured versioned migrations to a clean official Supabase project and checks their recorded versions. It uses independent database and Storage volumes and ports `55321`, `55322`, `55320` and local Mailpit `55324`. The encrypted configuration and ES256 signing keys are restored; a second empty database receives the dump and must match all table and policy digests before API checks. Newly generated Auth/Data/Storage services connect only to that recovered database. Their captured signing bindings are restored, including the legacy HMAC JWK. Auth and Storage keep their original health probes and use explicit empty HTTP proxy variables for internal local HTTP; HTTPS verification and its proxy are preserved.

The API rehearsal verifies signup remains disabled, refreshes a recovered existing MFA administrator session, signs into recovered accounts with their real passwords, verifies a recovered TOTP factor and administrator MFA upgrade, and checks each role through the real Data API. It downloads recovered private uploads through the real Storage API with checksum comparison and negative access checks, writes and reads a new authorized upload, and verifies password-recovery email reaches the independent local Mailpit instance. It never signs users out of the source. The separate project and its volumes are removed afterwards; private configuration, startup logs and the report remain outside the checkout. Without `--runtime-api`, only the isolated SQL and file-byte rehearsal runs.

The existing and fresh CLI cluster roles are compared with the captured inventory; the encrypted global-role export is never replayed into the source cluster. Recovery of custom global roles into a differently configured cluster remains untested. New backup sets include all four Edge handlers and server bindings inside encryption. The runtime clone restores these exact captured handlers, checks anonymous invitation denial and publication-only photo bytes, and exercises new anonymous capture, server pricing, retries and the separate WhatsApp activity. CRM fixtures additionally check recovered booking prices and Sales assignment boundaries. Older sets without these artifacts retain the documented Edge recovery limitation. Local Auth/MFA/signing, private uploads, published content/catalogue and publication-media visibility are checked by the runtime option, but hosted SMTP/DNS/accounts, hosted secret rebinding, external retention and production cutover remain separate prerequisites. No production backup, paid recovery feature or automatic restore is configured. Never run a database restore automatically because website code was rolled back.

Execution evidence and any current limitations are recorded by the development stage report after these commands actually run. The existence of these scripts alone is not a tested backup.
