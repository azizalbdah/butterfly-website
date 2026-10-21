# Enquiries and customer work

The dashboard uses real Supabase records. New projects have empty states rather
than demonstration counts. Admin must finish MFA to access CRM or assignments;
Sales can read and maintain only assigned enquiries and their related contacts,
companies and activity. Marketing has content/media permissions and no CRM
access. Database policies and scoped actions enforce these boundaries even when
someone calls the API directly. Deactivation and reassignment take effect
without waiting for an old access token to expire.

## Customer journey and prices

With a configured backend, catering and corporate forms save through
`submit-enquiry`, confirm an actual receipt, and offer a separate explicit
WhatsApp step. They require a phone or email without requiring customer login.
Catering names remain optional; corporate requests require company and contact
names. Identical retries, including simultaneous retries and retries after a
price publication, return the saved receipt. A changed payload needs a new key;
stale package revisions require refreshing and reviewing the estimate.

The server validates choices, contact details, dates, body size and approved
origins, rejects client prices/assignment, and calculates against the current
published catalogue using the same pricing engine as the calculator. Atomic
budgets permit three requests per contact in ten minutes and forty total per
minute. Contact keys are HMAC hashes using a server secret. A honeypot adds a
simple bot check. These controls do not claim CAPTCHA or identity verification;
monitor actual hosted traffic and tune operational limits before release.

Original contact/request details, catalogue revision, package/rate labels and
price breakdown are frozen on the enquiry. Quotations and bookings retain their
own immutable accepted price snapshots. A new catalogue affects new requests;
it never recalculates prior work. Above-capacity and corporate work require an
MFA administrator's explicit price approval with a reason and reference.

An unconfigured baseline website retains its original WhatsApp-only journey.
A configured backend outage reports failure and does not invent a saved record.
Unknown network outcomes can retry with the same request key. Public forms keep
contact data only in the current page, without persisting it in browser storage.

## Staff workflow

1. Admin triages New enquiries and assigns active Sales staff. Staff can switch
   between the six-column board and searchable table with pagination.
2. Assigned staff record Contacted, next action, follow-up and internal notes.
   Notes and activity are append-only. Concurrent edits require reloading rather
   than silently overwriting newer work.
3. After actually sending a quotation through the team's existing channel,
   record its reference and channel with **Record quotation sent**. This action
   records a human assertion; the app does not send the quotation or verify
   delivery. Custom/revised amounts need administrator approval first.
4. Use **Confirm booking** only after actual agreement, with a booking reference
   and the selected quotation/approved estimate. This separate action moves the
   record to Confirmed. Complete work when its event date has arrived. Closing
   as Lost requires a reason and cancels an active booking. Reopening completed
   work requires Admin, a reason and a return to Confirmed.

Opening WhatsApp records only `whatsapp_open_requested` with
`message_sent_verified=false`. Saving an enquiry, opening WhatsApp, recording
a quotation sent and confirming a booking are distinct events. Existing Foodics,
Ordable and Respond.io links/roles remain; no new integration or message-delivery
verification is connected.

## Contacts, history and dates

Exact normalized named contact + phone/email + company can share a customer
record. Shared phone numbers with different names, different companies, and
unnamed people are kept separate. Staff can explicitly correct a customer link
with a reason; only Admin can change company-wide contacts or company links.
Manual contact-check flags reflect staff checks and do not claim OTP verification.
Original submitted contact details remain visible after profile corrections.
Related records and paginated activity obey the same assignment restrictions.

Dates/times display in **Asia/Kuwait**. Overview date filters apply to received
date for enquiries/pipeline, due date for overdue follow-ups, actual recorded
sent date for quotations and confirmation date for active/completed bookings.
Cancelled bookings are excluded from the confirmed count. Completed/Lost work
is excluded from overdue. Date ranges include Kuwait midnight at the start and
exclude midnight after the final day. Blank filters mean all dates. Enquiry
search filters use received dates, so its count need not match other activity
metrics for the same range.

## Acceptance and deployment

`tests/crm_acceptance.py` checks the real local APIs, permissions, calculations,
history, concurrency, budgets and Kuwait boundaries. Run
`tests/crm_browser_acceptance.py` against a fresh configured public export on
port 8003 and the staff app on 5173. It exercises real public forms and staff
actions in both languages without mocked Auth or database responses. Test
fixtures are private local identities; they are never production seed data.

Production remains on the saved baseline. Follow [HOSTED_SETUP.md](HOSTED_SETUP.md)
for the owner-controlled project, SMTP and hosts, and rerun hosted acceptance
before release. Website rollback restores code only, preserving newer enquiries,
bookings, customer history and uploads. Backend recovery is a separate operation.
