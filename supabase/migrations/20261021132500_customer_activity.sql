create function public.list_customer_activity(target_id uuid,company_record boolean default false,page_size integer default 100,page_offset integer default 0)
returns setof jsonb language sql stable security invoker set search_path='' as $$
 select to_jsonb(a)||jsonb_build_object('receipt',e.receipt) from public.enquiry_activities a join public.enquiries e on e.id=a.enquiry_id
 where (not company_record and e.customer_id=target_id) or (company_record and e.company_id=target_id)
 order by a.created_at desc,a.id desc limit least(greatest(coalesce(page_size,100),1),100) offset least(greatest(coalesce(page_offset,0),0),100000);
$$;
revoke all on function public.list_customer_activity(uuid,boolean,integer,integer) from public,anon;
grant execute on function public.list_customer_activity(uuid,boolean,integer,integer) to authenticated;

create or replace function public.update_company(target_id uuid,expected_version bigint,new_name text,new_phone text,new_email text,verified_contact boolean)
returns public.companies language plpgsql security definer set search_path='' as $$
declare previous public.companies;result public.companies;item record;
begin
 if not public.app_is_admin() then raise exception 'Administrator MFA is required for company changes.' using errcode='42501'; end if;
 select * into previous from public.companies where id=target_id for update;
 if not found then raise exception 'Company not found.' using errcode='22023'; end if;
 if previous.version is distinct from expected_version then raise exception 'Company changed. Reload.' using errcode='PT409'; end if;
 new_name:=btrim(new_name);new_phone:=nullif(btrim(new_phone),'');new_email:=nullif(lower(btrim(new_email)),'');
 if new_name is null or char_length(new_name) not between 1 and 160 or new_name~'[[:cntrl:]]' or verified_contact is null or
  (new_phone is not null and new_phone!~'^\+[1-9][0-9]{7,14}$') or
  (new_email is not null and (char_length(new_email)>254 or new_email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')) then
  raise exception 'Check company contact details.' using errcode='22023'; end if;
 update public.companies set name=new_name,phone=new_phone,email=new_email,contact_verified=verified_contact,
  identity_key=public.crm_identity(array['company',public.crm_name_key(new_name),coalesce(new_phone,''),coalesce(new_email,'')]),
  version=version+1,updated_at=now() where id=target_id returning * into result;
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes)
  values(auth.uid(),'crm.company_updated','company',target_id,jsonb_build_object('before',to_jsonb(previous),'after',to_jsonb(result)));
 for item in select id from public.enquiries where company_id=target_id loop
  perform public.crm_event(item.id,'company_updated',jsonb_build_object('company_id',target_id));
 end loop;
 return result;
end;
$$;
