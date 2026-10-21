# Content and package publishing

The staff editor uses real Supabase data. Its local acceptance covers designated
content across all four public pages, package forms, private photos, public
rendering and immutable history. No hosted staff project or production publishing
connection is configured.

The import contains 472 fields: Arabic/English text, photos and descriptions,
links and contact destinations, titles, descriptions and social SEO metadata.
The original calculator's separate language handler supplies the catering SEO
title in both languages. The corrected imported content seed is
`10000000-0000-4000-8000-000000000003`; the approved catalogue seed is
`10000000-0000-4000-8000-000000000002`. The earlier import remains in private
history. A forward migration adds the correction without rewriting revisions or
replacing a draft whose other content was changed.

Marketing can save content drafts and upload private photos. An administrator
with a live MFA session can edit prices and publish. Sales can read the same
published catalogue as any visitor, but cannot access drafts or version history.
Raw client writes to revisions, head pointers, published media and audit history
are denied. Publishing and saving both recheck database permissions; anonymous,
inactive, uninvited and revoked sessions are denied.

Every save creates a new immutable revision. Saves include the draft ID the
editor loaded; a concurrent save receives HTTP 409 and cannot overwrite newer
work. Publishing checks both the current draft and publication IDs in a locked
transaction. Publishing applies to the complete saved content document or
complete catalogue. Version-history restoration loads an older payload into a
new draft and publishes a new revision; it does not erase history. Older history
is available through the editor's pagination.

The preview renders the actual public page template with draft text and photos.
It removes scripts, tracking, active forms, navigation and event handlers, uses
safe DOM text, and confines styles/images/fonts with CSP. Arabic/English and RTL
follow the staff language choice. Package previews use the same pricing module
as the public calculator. The private UI never executes arbitrary content HTML.

New PNG/JPG/WebP/AVIF photos up to 5 MB first enter private `staff-media`.
Publishing checks actual format signatures and hashes the exact bytes. It copies
them into private immutable objects in `site-media` before the database
transaction. A failed publish leaves those copies private. The transaction
registers only successfully published media; the anonymous `site-media` Edge
endpoint serves only registered hashes. Storage's direct public-object route
cannot read either bucket. Previously published photos stay available for old
versions; website rollback must not delete them. No automatic media deletion or
garbage collection is configured.

Public pages call only `get_published_site`, which returns the current content and
catalogue plus their immutable version IDs. Draft IDs are not accepted by that
API. Without a configured backend, the static site uses its approved imported
baseline. With a configured backend, a loading/failure state blocks unavailable
package estimates rather than silently quoting a stale baseline price. Contact
and ordering links remain public. The public calculator and private preview use
`assets/pricing.mjs`; prices and capacities come from the published catalogue.
The preserved recommendation rules are fixed and cannot be changed through the
price editor. Prices permit up to three decimal places in Kuwaiti dinars.

Build a separate configured public preview from an ignored private local status
file or a public-only JSON file containing `supabaseUrl` and `publishableKey`:

```bash
python3 scripts/build-public-preview.py --destination /tmp/butterfly-public-preview-NEW
python3 scripts/serve-public.py --root /tmp/butterfly-public-preview-NEW --port 8002
```

The exporter refuses privileged keys, existing destinations, hidden private files
and symlinks. It copies only public files/assets and omits the production CNAME.
No backend configuration, staff environment, Git metadata, backup or server key
belongs in that export. The source runtime configuration stays unconfigured;
building a preview does not alter the production website.

The importer is a one-time regeneration utility, not a startup command. It refuses
to replace public HTML containing later changes. To inspect a fresh regeneration,
use `python3 scripts/import-site-baseline.py --destination /tmp/import-review-NEW`
and review individual changes; do not overwrite later enquiry-capture code or
owner edits with an old baseline.

Acceptance commands:

```bash
node tests/pricing_parity.mjs
python3 tests/publishing_acceptance.py
python3 tests/publishing_browser_acceptance.py
```

The pricing test compares 55,494 cases with the actual saved Git version. The API
suite tests direct permissions, validation, concurrent saves/publishes, private
drafts and staged media, immutable history, public file bytes and audit actors.
The browser suite uses real accounts and APIs to edit, preview, publish, restore
versions and verify public prices, bilingual SEO/text, photo uploads, RTL/mobile
and absence of private-screen tracking. These tests create only local development
fixtures and restore the local approved publication through normal APIs. See the
stage checkpoint report for actual outcomes and recovery limits.
