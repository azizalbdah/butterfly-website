-- Preserve optional catering names; unnamed contacts are never automatically merged.
create or replace function public.capture_website_enquiry(
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
