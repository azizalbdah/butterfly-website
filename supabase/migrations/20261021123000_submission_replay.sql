-- Retry a lost response before recalculating against a newer published catalogue.
create function public.lookup_website_enquiry(request_key uuid,request_fingerprint text) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare previous public.enquiry_submissions;receipt_value text;
begin
 if auth.role() is distinct from 'service_role' then raise exception 'Server capture is required.' using errcode='42501'; end if;
 select * into previous from public.enquiry_submissions where submission_key=request_key;
 if not found then return null; end if;
 if previous.fingerprint is distinct from request_fingerprint then raise exception 'Submission key was already used for different details.' using errcode='PT409'; end if;
 select receipt into receipt_value from public.enquiries where id=previous.enquiry_id;
 return jsonb_build_object('receipt',receipt_value,'duplicate',true);
end;
$$;
revoke all on function public.lookup_website_enquiry(uuid,text) from public,anon,authenticated;
grant execute on function public.lookup_website_enquiry(uuid,text) to service_role;
