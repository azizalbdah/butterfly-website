-- Financial and original-submission snapshots stay immutable even for a
-- privileged API credential; operator SQL restore inserts do not rewrite them.
create function public.crm_freeze_snapshot() returns trigger language plpgsql set search_path='' as $$
begin
 if NEW.price_snapshot is distinct from OLD.price_snapshot then raise exception 'Price snapshots are immutable.' using errcode='42501'; end if;
 if TG_TABLE_NAME='enquiries' then
  if NEW.catalogue_revision is distinct from OLD.catalogue_revision or NEW.contact_snapshot is distinct from OLD.contact_snapshot
   or NEW.request_details is distinct from OLD.request_details or NEW.receipt is distinct from OLD.receipt then
   raise exception 'Submission snapshots are immutable.' using errcode='42501'; end if;
 elsif TG_TABLE_NAME='quotations' then
  if NEW.amount_fils is distinct from OLD.amount_fils or NEW.enquiry_id is distinct from OLD.enquiry_id or NEW.reference is distinct from OLD.reference
   or NEW.approved_at is distinct from OLD.approved_at or NEW.approved_by is distinct from OLD.approved_by then
   raise exception 'Quotation approval is immutable.' using errcode='42501'; end if;
  if OLD.sent_at is not null and (NEW.sent_at is distinct from OLD.sent_at or NEW.sent_by is distinct from OLD.sent_by or NEW.channel is distinct from OLD.channel) then
   raise exception 'Sent quotation history is immutable.' using errcode='42501'; end if;
 elsif TG_TABLE_NAME='bookings' then
  if NEW.amount_fils is distinct from OLD.amount_fils or NEW.enquiry_id is distinct from OLD.enquiry_id or NEW.reference is distinct from OLD.reference
   or NEW.quotation_id is distinct from OLD.quotation_id or NEW.confirmed_at is distinct from OLD.confirmed_at or NEW.confirmed_by is distinct from OLD.confirmed_by then
   raise exception 'Booking confirmation is immutable.' using errcode='42501'; end if;
 end if;
 return NEW;
end;
$$;
revoke all on function public.crm_freeze_snapshot() from public,anon,authenticated;
create trigger enquiry_snapshot_fixed before update on public.enquiries for each row execute function public.crm_freeze_snapshot();
create trigger quotation_snapshot_fixed before update on public.quotations for each row execute function public.crm_freeze_snapshot();
create trigger booking_snapshot_fixed before update on public.bookings for each row execute function public.crm_freeze_snapshot();

create function public.link_enquiry_customer(target_id uuid,target_customer_id uuid,expected_version bigint,link_reason text)
returns public.enquiries language plpgsql security definer set search_path='' as $$
declare result public.enquiries;customer public.customers;old_customer uuid;
begin
 result:=public.crm_get_for_update(target_id);
 if result.version is distinct from expected_version then raise exception 'Enquiry changed. Reload.' using errcode='PT409'; end if;
 if not public.crm_can_read_customer(target_customer_id) then raise exception 'Customer access is unavailable.' using errcode='42501'; end if;
 if link_reason is null or char_length(btrim(link_reason)) not between 1 and 1000 then raise exception 'Explain the customer correction.' using errcode='22023'; end if;
 select * into customer from public.customers where id=target_customer_id;
 if not found then raise exception 'Customer not found.' using errcode='22023'; end if;
 old_customer:=result.customer_id;
 update public.enquiries set customer_id=target_customer_id,company_id=customer.company_id,version=version+1,updated_at=now()
  where id=target_id returning * into result;
 perform public.crm_event(target_id,'customer_linked',jsonb_build_object('before',old_customer,'after',target_customer_id,'reason',btrim(link_reason)));
 return result;
end;
$$;
create function public.update_company(target_id uuid,expected_version bigint,new_name text,new_phone text,new_email text,verified_contact boolean)
returns public.companies language plpgsql security definer set search_path='' as $$
declare previous public.companies;result public.companies;
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
 return result;
end;
$$;
revoke all on function public.link_enquiry_customer(uuid,uuid,bigint,text),public.update_company(uuid,bigint,text,text,text,boolean) from public,anon;
grant execute on function public.link_enquiry_customer(uuid,uuid,bigint,text),public.update_company(uuid,bigint,text,text,text,boolean) to authenticated;

create or replace function public.update_enquiry(
 target_id uuid,expected_version bigint,new_status public.enquiry_status,
 new_next_action text default null,new_follow_up_at timestamptz default null,
 new_loss_reason text default null,change_note text default null
) returns public.enquiries language plpgsql security definer set search_path='' as $$
declare result public.enquiries;previous public.enquiries;
begin
 previous:=public.crm_get_for_update(target_id);
 if previous.version is distinct from expected_version then raise exception 'Enquiry changed. Reload.' using errcode='PT409'; end if;
 if new_status is null or char_length(coalesce(new_next_action,''))>500 or char_length(coalesce(new_loss_reason,''))>1000 or
  char_length(coalesce(change_note,''))>4000 then raise exception 'Invalid follow-up or status details.' using errcode='22023'; end if;
 if new_follow_up_at is not null and nullif(btrim(new_next_action),'') is null then
  raise exception 'A follow-up needs a next action.' using errcode='22023'; end if;
 if new_status in ('quotation_sent','confirmed') and new_status<>previous.status and not (previous.status='completed' and new_status='confirmed' and public.app_is_admin()) then
  raise exception 'Use the quotation or booking action with its reference.' using errcode='22023'; end if;
 if new_status='lost' and nullif(btrim(new_loss_reason),'') is null then raise exception 'A loss reason is required.' using errcode='22023'; end if;
 if previous.status in ('completed','lost') and new_status<>previous.status then
  if nullif(btrim(change_note),'') is null or (previous.status='completed' and not public.app_is_admin()) then
   raise exception 'Reopening needs a reason; completed work requires an administrator.' using errcode='42501'; end if;
 end if;
 if previous.status='confirmed' and new_status not in ('confirmed','completed','lost') then
  raise exception 'Complete or cancel the confirmed booking before changing its pipeline stage.' using errcode='22023'; end if;
 if previous.status='completed' and new_status<>'completed' then
  if new_status<>'confirmed' then raise exception 'Reopen completed work to Confirmed first, with an administrator reason.' using errcode='22023'; end if;
  update public.bookings set status='confirmed' where enquiry_id=target_id and status='completed';
 end if;
 if new_status='completed' and previous.status<>'completed' then
  if previous.status<>'confirmed' or not exists(select 1 from public.bookings where enquiry_id=target_id and status='confirmed') then
   raise exception 'Confirm a booking before completing it.' using errcode='22023'; end if;
  if previous.event_date is not null and previous.event_date>(now() at time zone 'Asia/Kuwait')::date then
   raise exception 'The event date has not arrived.' using errcode='22023'; end if;
  update public.bookings set status='completed' where enquiry_id=target_id and status='confirmed';
 end if;
 if new_status='lost' and previous.status='confirmed' then
  update public.bookings set status='cancelled',cancelled_at=now() where enquiry_id=target_id and status='confirmed';
  perform public.crm_event(target_id,'booking_cancelled',jsonb_build_object('reason',btrim(new_loss_reason)));
 end if;
 update public.enquiries set status=new_status,next_action=nullif(btrim(new_next_action),''),follow_up_at=new_follow_up_at,
  loss_reason=case when new_status='lost' then btrim(new_loss_reason) else null end,version=version+1,updated_at=now()
  where id=target_id returning * into result;
 perform public.crm_event(target_id,case when previous.status<>new_status then 'status_changed' else 'followup_updated' end,
  jsonb_build_object('before',previous.status,'after',new_status,'next_action',result.next_action,'follow_up_at',new_follow_up_at,'loss_reason',result.loss_reason,'note',nullif(btrim(change_note),'')));
 return result;
end;
$$;
create or replace function public.record_quotation_sent(target_id uuid,quote_reference text,sent_channel public.quotation_channel,approved_quote_id uuid default null)
returns public.quotations language plpgsql security definer set search_path='' as $$
declare enquiry public.enquiries;result public.quotations;snapshot jsonb;amount bigint;
begin
 enquiry:=public.crm_get_for_update(target_id);
 if enquiry.status in ('confirmed','completed','lost') or quote_reference is null or char_length(btrim(quote_reference)) not between 1 and 120 or sent_channel is null then
  raise exception 'Use an active enquiry and an actual sent quotation reference/channel.' using errcode='22023'; end if;
 if approved_quote_id is not null then
  select * into result from public.quotations where id=approved_quote_id and enquiry_id=target_id for update;
  if not found or result.reference is distinct from btrim(quote_reference) then raise exception 'Approved quotation not found.' using errcode='22023'; end if;
 else
  select * into result from public.quotations where enquiry_id=target_id and reference=btrim(quote_reference) for update;
  if not found then
   if coalesce((enquiry.price_snapshot->>'requires_custom_quote')::boolean,true) or enquiry.price_snapshot->>'total_fils' is null then
    raise exception 'Ask an administrator to approve this tailored quotation first.' using errcode='42501'; end if;
   amount:=(enquiry.price_snapshot->>'total_fils')::bigint;
   snapshot:=enquiry.price_snapshot||jsonb_build_object('contact',enquiry.contact_snapshot,'source','published_catalogue');
   insert into public.quotations(enquiry_id,reference,amount_fils,price_snapshot)
    values(target_id,btrim(quote_reference),amount,snapshot) returning * into result;
  end if;
 end if;
 if result.sent_at is not null then
  if enquiry.status<>'quotation_sent' then
   update public.enquiries set status='quotation_sent',version=version+1,updated_at=now() where id=target_id;
   perform public.crm_event(target_id,'status_changed',jsonb_build_object('before',enquiry.status,'after','quotation_sent','existing_quotation',result.id));
  end if;
  return result;
 end if;
 update public.quotations set sent_by=auth.uid(),sent_at=now(),channel=sent_channel where id=result.id returning * into result;
 update public.enquiries set status='quotation_sent',version=version+1,updated_at=now() where id=target_id;
 perform public.crm_event(target_id,'quotation_sent',jsonb_build_object('quotation_id',result.id,'reference',result.reference,'channel',sent_channel,'total_fils',result.amount_fils));
 return result;
end;
$$;

