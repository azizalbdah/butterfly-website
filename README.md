# Butterfly website and staff workspace

The public customer website is static HTML/CSS/JavaScript. A separate private
staff client under `staff/` connects to Supabase Auth, Postgres and Storage.
The production website remains on its preserved baseline while staged dashboard
work is developed on the feature branch.

- [Delivery status and stage acceptance](docs/DELIVERY_PLAN.md)
- [Verified website baseline and rollback](ROLLBACK.md)
- [Local preview and acceptance commands](docs/LOCAL_PREVIEW.md)
- [Supabase setup and external prerequisites](docs/SUPABASE_SETUP.md)
- [Exact owner-controlled hosted setup steps](docs/HOSTED_SETUP.md)
- [Content, package editing and safe publishing](docs/PUBLISHING.md)
- [Enquiry, customer and quotation workflow](docs/CRM.md)
- [Later release boundaries](docs/FUTURE_RELEASE.md)
- [Separate backend recovery requirements](docs/BACKEND_RECOVERY.md)
- [Encrypted local backup and tested recovery procedure](docs/LOCAL_RECOVERY.md)

Run `python3 scripts/serve-public.py --port 8000` for the restricted public-site
preview. Follow the local preview guide for the genuine staff backend and client.
Never serve the entire checkout with an unrestricted static server or commit
credentials, private backups or staff/customer data.
