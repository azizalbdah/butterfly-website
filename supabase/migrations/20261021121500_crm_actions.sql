-- All staff mutations verify the live session, role, assignment and concurrency.
create function public.assign_enquiry(target_id uuid,assignee_id uuid,expected_version bigint)
returns public.enquiries language plpgsql security definer set search_path='' as $$
declare result public.enquiries;previous_assignee uuid;
begin
 if not public.app_is_admin() then raise exception 'Administrator MFA is required.' using errcode='42501'; end if;
 select * into result from public.enquiries where id=target_id for update;
 if not found then raise exception 'Enquiry not found.' using errcode='P0002'; end if;
 if result.version is distinct from expected_version then raise exception 'Enquiry changed. Reload.' using errcode='PT409'; end if;
 if assignee_id is not null and not exists(select 1 from public.staff_members where user_id=assignee_id and active and role='sales') then
  raise exception 'Choose an active Sales colleague.' using errcode='22023'; end if;
 previous_assignee:=result.assigned_to;
 update public.enquiries set assigned_to=assignee_id,version=version+1,updated_at=now() where id=target_id returning * into result;
 perform public.crm_event(target_id,'assigned',jsonb_build_object('before',previous_assignee,'after',assignee_id));
 return result;
end;
$$;

create function public.update_enquiry(
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
 if new_status in ('quotation_sent','confirmed') and new_status<>previous.status then
  raise exception 'Use the quotation or booking action with its reference.' using errcode='22023'; end if;
 if new_status='lost' and nullif(btrim(new_loss_reason),'') is null then raise exception 'A loss reason is required.' using errcode='22023'; end if;
 if previous.status in ('completed','lost') and new_status<>previous.status then
  if nullif(btrim(change_note),'') is null or (previous.status='completed' and not public.app_is_admin()) then
   raise exception 'Reopening needs a reason; completed work requires an administrator.' using errcode='42501'; end if;
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
create function public.add_enquiry_note(target_id uuid,note_text text) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.crm_get_for_update(target_id);
 if note_text is null or char_length(btrim(note_text)) not between 1 and 4000 then raise exception 'Write a note up to 4000 characters.' using errcode='22023'; end if;
 perform public.crm_event(target_id,'note_added',jsonb_build_object('note',btrim(note_text)));
end;
$$;

create function public.approve_quotation(target_id uuid,quote_reference text,total_fils bigint,approval_reason text)
returns public.quotations language plpgsql security definer set search_path='' as $$
declare enquiry public.enquiries;result public.quotations;snapshot jsonb;
begin
 if not public.app_is_admin() then raise exception 'Administrator MFA is required to approve prices.' using errcode='42501'; end if;
 enquiry:=public.crm_get_for_update(target_id);
 if enquiry.status in ('completed','lost') or quote_reference is null or char_length(btrim(quote_reference)) not between 1 and 120 or
  total_fils is null or total_fils not between 0 and 1000000000000 or approval_reason is null or char_length(btrim(approval_reason)) not between 1 and 1000 then
  raise exception 'Supply an active enquiry, quotation reference, approved amount and reason.' using errcode='22023'; end if;
 snapshot:=jsonb_build_object('schema',1,'source','administrator_approval','total_fils',total_fils,
  'catalogue_revision',enquiry.catalogue_revision,'original_estimate',enquiry.price_snapshot,
  'approval_reason',btrim(approval_reason),'contact',enquiry.contact_snapshot);
 insert into public.quotations(enquiry_id,reference,amount_fils,price_snapshot,approved_by)
  values(target_id,btrim(quote_reference),total_fils,snapshot,auth.uid()) returning * into result;
 perform public.crm_event(target_id,'quotation_approved',jsonb_build_object('quotation_id',result.id,'reference',result.reference,'total_fils',total_fils,'reason',btrim(approval_reason)));
 return result;
end;
$$;
create function public.record_quotation_sent(target_id uuid,quote_reference text,sent_channel public.quotation_channel,approved_quote_id uuid default null)
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
 if result.sent_at is not null then return result; end if;
 update public.quotations set sent_by=auth.uid(),sent_at=now(),channel=sent_channel where id=result.id returning * into result;
 update public.enquiries set status='quotation_sent',version=version+1,updated_at=now() where id=target_id;
 perform public.crm_event(target_id,'quotation_sent',jsonb_build_object('quotation_id',result.id,'reference',result.reference,'channel',sent_channel,'total_fils',result.amount_fils));
 return result;
end;
$$;

create function public.confirm_booking(target_id uuid,booking_reference text,expected_version bigint,approved_quote_id uuid default null)
returns public.bookings language plpgsql security definer set search_path='' as $$
declare enquiry public.enquiries;quote public.quotations;result public.bookings;snapshot jsonb;amount bigint;
begin
 enquiry:=public.crm_get_for_update(target_id);
 if enquiry.version is distinct from expected_version then raise exception 'Enquiry changed. Reload.' using errcode='PT409'; end if;
 if booking_reference is null or char_length(btrim(booking_reference)) not between 1 and 120 or enquiry.status in ('completed','lost') then
  raise exception 'Use an active enquiry and an actual booking confirmation reference.' using errcode='22023'; end if;
 select * into result from public.bookings where enquiry_id=target_id and status='confirmed';
 if found then
  if result.reference=btrim(booking_reference) then return result; end if;
  raise exception 'An active booking already exists.' using errcode='PT409';
 end if;
 if approved_quote_id is not null then
  select * into quote from public.quotations where id=approved_quote_id and enquiry_id=target_id;
  if not found then raise exception 'Quotation not found for this enquiry.' using errcode='22023'; end if;
 else
  select * into quote from public.quotations where enquiry_id=target_id order by approved_at desc limit 1;
 end if;
 if quote.id is not null then snapshot:=quote.price_snapshot;amount:=quote.amount_fils;
 else
  if coalesce((enquiry.price_snapshot->>'requires_custom_quote')::boolean,true) or enquiry.price_snapshot->>'total_fils' is null then
   raise exception 'An administrator must approve the tailored price before booking.' using errcode='42501'; end if;
  snapshot:=enquiry.price_snapshot||jsonb_build_object('contact',enquiry.contact_snapshot,'source','published_catalogue');
  amount:=(snapshot->>'total_fils')::bigint;
 end if;
 insert into public.bookings(enquiry_id,quotation_id,reference,amount_fils,price_snapshot,confirmed_by)
  values(target_id,quote.id,btrim(booking_reference),amount,snapshot,auth.uid()) returning * into result;
 update public.enquiries set status='confirmed',version=version+1,updated_at=now() where id=target_id;
 perform public.crm_event(target_id,'booking_confirmed',jsonb_build_object('booking_id',result.id,'reference',result.reference,'total_fils',amount));
 return result;
end;
$$;

create function public.update_customer(target_id uuid,expected_version bigint,new_name text,new_phone text,new_email text,verified_contact boolean)
returns public.customers language plpgsql security definer set search_path='' as $$
declare previous public.customers;result public.customers;identity text;item record;
begin
 if not public.crm_can_read_customer(target_id) then raise exception 'Customer access is unavailable.' using errcode='42501'; end if;
 select * into previous from public.customers where id=target_id for update;
 if previous.version is distinct from expected_version then raise exception 'Customer changed. Reload.' using errcode='PT409'; end if;
 new_name:=btrim(new_name);new_phone:=nullif(btrim(new_phone),'');new_email:=nullif(lower(btrim(new_email)),'');
 if new_name is null or char_length(new_name) not between 1 and 120 or new_name~'[[:cntrl:]]' or verified_contact is null or
  (new_phone is null and new_email is null) or (new_phone is not null and new_phone!~'^\+[1-9][0-9]{7,14}$') or
  (new_email is not null and (char_length(new_email)>254 or new_email!~'^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')) then
  raise exception 'Supply a name and valid phone/email.' using errcode='22023'; end if;
 identity:=public.crm_identity(array['customer',coalesce(previous.company_id::text,''),public.crm_name_key(new_name),coalesce(new_phone,''),coalesce(new_email,'')]);
 update public.customers set display_name=new_name,phone=new_phone,email=new_email,identity_key=identity,contact_verified=verified_contact,
  version=version+1,updated_at=now() where id=target_id returning * into result;
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes) values(auth.uid(),'crm.customer_updated','customer',target_id,jsonb_build_object('before',to_jsonb(previous),'after',to_jsonb(result)));
 for item in select id from public.enquiries where customer_id=target_id and public.crm_can_read_enquiry(id) loop
  perform public.crm_event(item.id,'customer_updated',jsonb_build_object('customer_id',target_id));
 end loop;
 return result;
end;
$$;
create function public.link_customer_company(target_customer_id uuid,target_company_id uuid,expected_version bigint)
returns public.customers language plpgsql security definer set search_path='' as $$
declare result public.customers;previous_company uuid;item record;
begin
 if not public.app_is_admin() then raise exception 'Administrator MFA is required.' using errcode='42501'; end if;
 select * into result from public.customers where id=target_customer_id for update;
 if not found then raise exception 'Customer not found.' using errcode='P0002'; end if;
 if result.version is distinct from expected_version then raise exception 'Customer changed. Reload.' using errcode='PT409'; end if;
 if target_company_id is not null and not exists(select 1 from public.companies where id=target_company_id) then raise exception 'Company not found.' using errcode='22023'; end if;
 previous_company:=result.company_id;
 update public.customers set company_id=target_company_id,
  identity_key=public.crm_identity(array['customer',coalesce(target_company_id::text,''),public.crm_name_key(display_name),coalesce(phone,''),coalesce(email,'')]),
  version=version+1,updated_at=now() where id=target_customer_id returning * into result;
 update public.enquiries set company_id=target_company_id,version=version+1,updated_at=now() where customer_id=target_customer_id;
 for item in select id from public.enquiries where customer_id=target_customer_id loop
  perform public.crm_event(item.id,'company_linked',jsonb_build_object('customer_id',target_customer_id,'before',previous_company,'after',target_company_id));
 end loop;
 return result;
end;
$$;

create function public.get_crm_overview(date_from date default null,date_to date default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare start_at timestamptz;end_at timestamptz;pipeline jsonb;received bigint;overdue bigint;sent bigint;confirmed bigint;
begin
 if not coalesce(public.app_is_admin() or public.app_staff_role()='sales',false) then raise exception 'Sales or administrator access is required.' using errcode='42501'; end if;
 if date_from is not null and date_to is not null and date_to<date_from then raise exception 'Check the date range.' using errcode='22023'; end if;
 start_at:=date_from::timestamp at time zone 'Asia/Kuwait';end_at:=(date_to+1)::timestamp at time zone 'Asia/Kuwait';
 select count(*) into received from public.enquiries e where public.crm_can_read_enquiry(e.id) and (start_at is null or e.created_at>=start_at) and (end_at is null or e.created_at<end_at);
 select jsonb_object_agg(s,coalesce(c.total,0)) into pipeline from unnest(enum_range(null::public.enquiry_status)) s
  left join (select status,count(*) total from public.enquiries e where public.crm_can_read_enquiry(e.id) and (start_at is null or e.created_at>=start_at) and (end_at is null or e.created_at<end_at) group by status)c on c.status=s;
 select count(*) into overdue from public.enquiries e where public.crm_can_read_enquiry(e.id) and e.status not in ('completed','lost') and e.follow_up_at<now()
  and (start_at is null or e.follow_up_at>=start_at) and (end_at is null or e.follow_up_at<end_at);
 select count(*) into sent from public.quotations q where public.crm_can_read_enquiry(q.enquiry_id) and q.sent_at is not null
  and (start_at is null or q.sent_at>=start_at) and (end_at is null or q.sent_at<end_at);
 select count(*) into confirmed from public.bookings b where public.crm_can_read_enquiry(b.enquiry_id) and b.status in ('confirmed','completed')
  and (start_at is null or b.confirmed_at>=start_at) and (end_at is null or b.confirmed_at<end_at);
 return jsonb_build_object('received',received,'overdue',overdue,'quotations_sent',sent,'confirmed_bookings',confirmed,'pipeline',pipeline,'checked_at',now(),'timezone','Asia/Kuwait');
end;
$$;

revoke all on function public.assign_enquiry(uuid,uuid,bigint),public.update_enquiry(uuid,bigint,public.enquiry_status,text,timestamptz,text,text),public.add_enquiry_note(uuid,text),
 public.approve_quotation(uuid,text,bigint,text),public.record_quotation_sent(uuid,text,public.quotation_channel,uuid),public.confirm_booking(uuid,text,bigint,uuid),
 public.update_customer(uuid,bigint,text,text,text,boolean),public.link_customer_company(uuid,uuid,bigint),public.get_crm_overview(date,date) from public,anon;
grant execute on function public.assign_enquiry(uuid,uuid,bigint),public.update_enquiry(uuid,bigint,public.enquiry_status,text,timestamptz,text,text),public.add_enquiry_note(uuid,text),
 public.approve_quotation(uuid,text,bigint,text),public.record_quotation_sent(uuid,text,public.quotation_channel,uuid),public.confirm_booking(uuid,text,bigint,uuid),
 public.update_customer(uuid,bigint,text,text,text,boolean),public.link_customer_company(uuid,uuid,bigint),public.get_crm_overview(date,date) to authenticated;
