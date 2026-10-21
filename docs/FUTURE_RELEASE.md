# Later release boundaries

The initial dashboard records quotations and bookings. The following features
remain a separate release, after requirements and acceptance are approved:

| Feature | Permissions and data to preserve | Required acceptance |
| --- | --- | --- |
| Quotation templates and PDF generation | Admin owns templates/price approval; Sales uses assigned enquiries. Each issued document freezes template version, language, customer/company details, line prices, totals and catalogue/approval reference. Store PDFs privately with authorized retrieval. | Bilingual typography/RTL, total parity, immutable reprints, accessible output, assignment denial, private file recovery and send-versus-delivery distinction. |
| Event scheduling | Admin coordinates resources; assigned staff see their permitted work. Booking snapshots remain immutable while scheduling changes are audited separately. | Kuwait time/date boundaries, conflicting bookings, cancellations, concurrent edits, resource permissions and recovery without losing later changes. |
| Customer portal | A separate customer identity and explicit record ownership; no staff role through metadata or email matching alone. Publish only approved customer-facing records. | Cross-customer isolation, invitation/ownership proof, expiry/revocation, mobile/RTL accessibility, private attachments and separate portal recovery. |

Do not infer these features from the current board, quotation references, event
date field or WhatsApp button. Existing external systems keep their current
roles until a separately tested integration is specified.
