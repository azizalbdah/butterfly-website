-- Stage D: private CRM records, immutable financial snapshots and scoped access.
create type public.enquiry_status as enum ('new','contacted','quotation_sent','confirmed','completed','lost');
create type public.quotation_channel as enum ('email','whatsapp','phone','other');

create table public.companies (
 id uuid primary key default gen_random_uuid(),
 name text not null check(char_length(btrim(name)) between 1 and 160),
 phone text, email text, identity_key text not null unique,
 contact_verified boolean not null default false,
 version bigint not null default 1,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now()
);
create table public.customers (
 id uuid primary key default gen_random_uuid(),
 company_id uuid references public.companies(id),
 display_name text not null check(char_length(btrim(display_name)) between 1 and 120),
 phone text,email text,identity_key text not null unique,
 contact_verified boolean not null default false,
 version bigint not null default 1,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 check(nullif(phone,'') is not null or nullif(email,'') is not null)
);
create table public.enquiries (
 id uuid primary key default gen_random_uuid(),
 receipt text not null unique,
 customer_id uuid not null references public.customers(id),
 company_id uuid references public.companies(id),
 assigned_to uuid references public.staff_members(user_id),
 status public.enquiry_status not null default 'new',
 source text not null default 'website' check(source in ('website','staff')),
 enquiry_kind text not null check(enquiry_kind in ('catering','corporate')),
 service text not null check(service in ('hospitality','wedding','coffee','corporate')),
 catalogue_revision uuid not null references public.site_revisions(id),
 price_snapshot jsonb not null check(jsonb_typeof(price_snapshot)='object'),
 contact_snapshot jsonb not null check(jsonb_typeof(contact_snapshot)='object'),
 request_details jsonb not null check(jsonb_typeof(request_details)='object'),
 event_date date,event_time time,venue text,
 next_action text check(char_length(next_action)<=500),follow_up_at timestamptz,
 loss_reason text check(char_length(loss_reason)<=1000),
 version bigint not null default 1,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 check(follow_up_at is null or coalesce(char_length(btrim(next_action)),0)>0),
 check(status<>'lost' or coalesce(char_length(btrim(loss_reason)),0)>0)
);
create index enquiry_assignee_received on public.enquiries(assigned_to,created_at desc);
create index enquiry_received on public.enquiries(created_at desc);
create index enquiry_customer on public.enquiries(customer_id,created_at desc);
create index enquiry_company on public.enquiries(company_id,created_at desc);
create index enquiry_followup on public.enquiries(follow_up_at) where status not in ('completed','lost');

-- Submission capabilities and fingerprints are never readable by staff clients.
create table public.enquiry_submissions (
 submission_key uuid primary key,enquiry_id uuid not null unique references public.enquiries(id),
 fingerprint text not null,created_at timestamptz not null default now()
);
create table public.enquiry_activities (
 id uuid primary key default gen_random_uuid(),
 enquiry_id uuid not null references public.enquiries(id),
 event_type text not null,actor_user_id uuid,actor_label text not null,
 details jsonb not null default '{}',created_at timestamptz not null default now()
);
create index enquiry_activity_history on public.enquiry_activities(enquiry_id,created_at);
create unique index enquiry_whatsapp_open_once on public.enquiry_activities(enquiry_id,event_type)
 where event_type='whatsapp_open_requested';
create table public.quotations (
 id uuid primary key default gen_random_uuid(),enquiry_id uuid not null references public.enquiries(id),
 reference text not null check(char_length(btrim(reference)) between 1 and 120),
 amount_fils bigint not null check(amount_fils between 0 and 1000000000000),
 price_snapshot jsonb not null,approved_by uuid,approved_at timestamptz not null default now(),
 sent_by uuid,sent_at timestamptz,channel public.quotation_channel,
 created_at timestamptz not null default now(),unique(enquiry_id,reference),
 check(price_snapshot->>'total_fils' is not null and (price_snapshot->>'total_fils')::bigint=amount_fils),
 check((sent_at is null and sent_by is null and channel is null) or
       (sent_at is not null and sent_by is not null and channel is not null))
);
create index quotation_sent_date on public.quotations(sent_at) where sent_at is not null;
create table public.bookings (
 id uuid primary key default gen_random_uuid(),enquiry_id uuid not null references public.enquiries(id),
 quotation_id uuid references public.quotations(id),reference text not null,
 amount_fils bigint not null check(amount_fils between 0 and 1000000000000),
 price_snapshot jsonb not null,
 status text not null default 'confirmed' check(status in ('confirmed','completed','cancelled')),
 confirmed_by uuid not null,confirmed_at timestamptz not null default now(),cancelled_at timestamptz,
 unique(enquiry_id,reference),check(char_length(btrim(reference)) between 1 and 120),
 check(price_snapshot->>'total_fils' is not null and (price_snapshot->>'total_fils')::bigint=amount_fils)
);
create unique index enquiry_one_active_booking on public.bookings(enquiry_id) where status in ('confirmed','completed');
create index booking_confirmation_date on public.bookings(confirmed_at);
create table public.crm_rate_limits (
 limit_key text primary key,request_count integer not null,expires_at timestamptz not null
);

alter table public.companies enable row level security;
alter table public.customers enable row level security;
alter table public.enquiries enable row level security;
alter table public.enquiry_submissions enable row level security;
alter table public.enquiry_activities enable row level security;
alter table public.quotations enable row level security;
alter table public.bookings enable row level security;
alter table public.crm_rate_limits enable row level security;
revoke all on public.companies,public.customers,public.enquiries,public.enquiry_submissions,
 public.enquiry_activities,public.quotations,public.bookings,public.crm_rate_limits from anon,authenticated;
grant select on public.companies,public.customers,public.enquiries,public.enquiry_activities,
 public.quotations,public.bookings to authenticated;
grant all on public.companies,public.customers,public.enquiries,public.enquiry_submissions,
 public.enquiry_activities,public.quotations,public.bookings,public.crm_rate_limits to service_role;

create function public.crm_can_read_enquiry(target_id uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select coalesce(public.app_is_admin() or (public.app_staff_role()='sales' and exists(
  select 1 from public.enquiries e where e.id=target_id and e.assigned_to=auth.uid())),false);
$$;
create function public.crm_can_read_customer(target_id uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select coalesce(public.app_is_admin() or (public.app_staff_role()='sales' and exists(
  select 1 from public.enquiries e where e.customer_id=target_id and e.assigned_to=auth.uid())),false);
$$;
create function public.crm_can_read_company(target_id uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select coalesce(public.app_is_admin() or (public.app_staff_role()='sales' and exists(
  select 1 from public.enquiries e where e.company_id=target_id and e.assigned_to=auth.uid())),false);
$$;
revoke all on function public.crm_can_read_enquiry(uuid),public.crm_can_read_customer(uuid),public.crm_can_read_company(uuid) from public,anon;
grant execute on function public.crm_can_read_enquiry(uuid),public.crm_can_read_customer(uuid),public.crm_can_read_company(uuid) to authenticated;
create policy crm_enquiry_read on public.enquiries for select to authenticated using(public.crm_can_read_enquiry(id));
create policy crm_customer_read on public.customers for select to authenticated using(public.crm_can_read_customer(id));
create policy crm_company_read on public.companies for select to authenticated using(public.crm_can_read_company(id));
create policy crm_activity_read on public.enquiry_activities for select to authenticated using(public.crm_can_read_enquiry(enquiry_id));
create policy crm_quotation_read on public.quotations for select to authenticated using(public.crm_can_read_enquiry(enquiry_id));
create policy crm_booking_read on public.bookings for select to authenticated using(public.crm_can_read_enquiry(enquiry_id));

create function public.crm_name_key(value text) returns text language sql immutable set search_path='' as $$
 select lower(regexp_replace(btrim(normalize(coalesce(value,''),NFKC)),'[[:space:]]+',' ','g'));
$$;
create function public.crm_identity(parts text[]) returns text language sql immutable set search_path='' as $$
 select encode(extensions.digest(array_to_string(parts,chr(31)),'sha256'),'hex');
$$;
create function public.crm_get_for_update(target_id uuid) returns public.enquiries
language plpgsql security definer set search_path='' as $$
declare result public.enquiries;
begin
 select * into result from public.enquiries where id=target_id for update;
 if not found or not coalesce(public.app_is_admin() or (public.app_staff_role()='sales' and result.assigned_to=auth.uid()),false) then
  raise exception 'Enquiry access is unavailable.' using errcode='42501'; end if;
 return result;
end;
$$;
create function public.crm_event(target_id uuid,event_name text,event_details jsonb default '{}') returns void
language plpgsql security definer set search_path='' as $$
declare actor uuid;label text;
begin
 if auth.role()='authenticated' then
  actor:=auth.uid();select display_name into label from public.staff_members where user_id=actor;
 else label:='Website visitor'; end if;
 insert into public.enquiry_activities(enquiry_id,event_type,actor_user_id,actor_label,details)
  values(target_id,event_name,actor,coalesce(label,'Staff'),event_details);
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes)
  values(actor,'crm.'||event_name,'enquiry',target_id,event_details);
end;
$$;
revoke all on function public.crm_name_key(text),public.crm_identity(text[]),public.crm_get_for_update(uuid),public.crm_event(uuid,text,jsonb) from public,anon,authenticated;

create function public.capture_website_enquiry(
 request_key uuid,request_fingerprint text,contact_rate_key text,
 catalogue_id uuid,submitted jsonb,pricing jsonb
) returns jsonb language plpgsql security definer set search_path='' as $$
declare previous public.enquiry_submissions;current_catalogue uuid;comp_id uuid;cust_id uuid;
 company_name text;person_name text;phone text;email text;identity text;result public.enquiries;
 count_value integer;bucket text;maximum integer;index_value integer;
begin
 -- Private service credential only; no anonymous direct RPC can bypass Edge validation.
 if auth.role() is distinct from 'service_role' then raise exception 'Server capture is required.' using errcode='42501'; end if;
 if request_key is null or request_fingerprint is null or contact_rate_key is null or request_fingerprint!~'^[a-f0-9]{64}$' or contact_rate_key!~'^[a-f0-9]{64}$' then
  raise exception 'Invalid submission.' using errcode='22023'; end if;
 -- Serialize identical keys without exposing capabilities through staff tables.
 perform pg_advisory_xact_lock(hashtextextended(request_key::text,0));
 select * into previous from public.enquiry_submissions where submission_key=request_key;
 if found then
  if previous.fingerprint is distinct from request_fingerprint then raise exception 'Submission key was already used for different details.' using errcode='PT409'; end if;
  select * into result from public.enquiries where id=previous.enquiry_id;
  return jsonb_build_object('receipt',result.receipt,'duplicate',true);
 end if;
 select published_id into current_catalogue from public.site_document_heads where kind='catalogue' for share;
 if current_catalogue is distinct from catalogue_id or pricing->>'catalogue_revision' is distinct from catalogue_id::text then
  raise exception 'Published prices changed. Review your estimate and submit again.' using errcode='PT409'; end if;
 if submitted->>'catalogue_revision' is distinct from catalogue_id::text then
  raise exception 'Published prices changed. Review your estimate and submit again.' using errcode='PT409'; end if;
 person_name:=coalesce(btrim(submitted->'customer'->>'name'),'');company_name:=nullif(btrim(submitted->'customer'->>'company'),'');
 phone:=nullif(submitted->'customer'->>'phone','');email:=nullif(lower(submitted->'customer'->>'email'),'');
 if char_length(person_name)>120 or person_name~'[[:cntrl:]]' or
  (phone is null and email is null) or (phone is not null and phone!~'^\+[1-9][0-9]{7,14}$') or
  (email is not null and (char_length(email)>254 or email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')) or
  (company_name is not null and char_length(company_name)>160) or jsonb_typeof(pricing)<>'object' or
  pricing->>'requires_custom_quote' is null then raise exception 'Invalid contact or estimate.' using errcode='22023'; end if;
 for index_value in 1..2 loop
  if index_value=1 then bucket:='all:'||floor(extract(epoch from now())/60)::bigint;maximum:=40;
  else bucket:='contact:'||contact_rate_key||':'||floor(extract(epoch from now())/600)::bigint;maximum:=3; end if;
  insert into public.crm_rate_limits(limit_key,request_count,expires_at) values(bucket,1,now()+interval '1 day')
   on conflict(limit_key) do update set request_count=public.crm_rate_limits.request_count+1 returning request_count into count_value;
  if count_value>maximum then raise exception 'Too many submissions. Try again later.' using errcode='PT429'; end if;
 end loop;
 delete from public.crm_rate_limits where expires_at<now();
 if company_name is not null then
  identity:=public.crm_identity(array['company',public.crm_name_key(company_name),coalesce(phone,''),coalesce(email,'')]);
  insert into public.companies(name,phone,email,identity_key) values(company_name,phone,email,identity)
   on conflict(identity_key) do nothing;
  select id into comp_id from public.companies where identity_key=identity;
 end if;
 identity:=public.crm_identity(array['customer',coalesce(comp_id::text,''),case when person_name='' then 'unnamed:'||request_key::text else public.crm_name_key(person_name) end,coalesce(phone,''),coalesce(email,'')]);
 insert into public.customers(company_id,display_name,phone,email,identity_key) values(comp_id,coalesce(nullif(person_name,''),phone,email),phone,email,identity)
  on conflict(identity_key) do nothing;
 select id into cust_id from public.customers where identity_key=identity;
 insert into public.enquiries(receipt,customer_id,company_id,enquiry_kind,service,catalogue_revision,price_snapshot,contact_snapshot,request_details,event_date,event_time,venue)
  values('BF-'||to_char(now() at time zone 'Asia/Kuwait','YYMMDD')||'-'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,10)),
   cust_id,comp_id,submitted->>'kind',submitted->>'service',catalogue_id,pricing,submitted->'customer',submitted,
   nullif(submitted->>'event_date','')::date,nullif(submitted->>'event_time','')::time,submitted->>'venue') returning * into result;
 insert into public.enquiry_submissions(submission_key,enquiry_id,fingerprint) values(request_key,result.id,request_fingerprint);
 perform public.crm_event(result.id,'submitted',jsonb_build_object('source','website','contact_verified',false));
 return jsonb_build_object('receipt',result.receipt,'duplicate',false);
end;
$$;
create function public.record_website_whatsapp_open(request_key uuid) returns void
language plpgsql security definer set search_path='' as $$
declare target_id uuid;
begin
 if auth.role() is distinct from 'service_role' then raise exception 'Server capture is required.' using errcode='42501'; end if;
 select enquiry_id into target_id from public.enquiry_submissions where submission_key=request_key;
 if target_id is null then return; end if;
 insert into public.enquiry_activities(enquiry_id,event_type,actor_label,details)
  values(target_id,'whatsapp_open_requested','Website visitor','{"message_sent_verified":false}') on conflict do nothing;
 -- Opening a link never changes pipeline, quotation or booking state.
end;
$$;
revoke all on function public.capture_website_enquiry(uuid,text,text,uuid,jsonb,jsonb),public.record_website_whatsapp_open(uuid) from public,anon,authenticated;
grant execute on function public.capture_website_enquiry(uuid,text,text,uuid,jsonb,jsonb),public.record_website_whatsapp_open(uuid) to service_role;
