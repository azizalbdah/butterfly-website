-- Parameterized search and pagination run as the caller: table RLS remains the
-- access boundary for every joined customer/company and enquiry.
create function public.list_enquiries(date_from date default null,date_to date default null,
 status_filter public.enquiry_status default null,search_query text default '',page_size integer default 100,page_offset integer default 0)
returns setof jsonb language sql stable security invoker set search_path='' as $$
 select to_jsonb(e)||jsonb_build_object('customer',to_jsonb(c),'company',to_jsonb(co))
 from public.enquiries e join public.customers c on c.id=e.customer_id left join public.companies co on co.id=e.company_id
 where (date_from is null or e.created_at>=date_from::timestamp at time zone 'Asia/Kuwait')
  and (date_to is null or e.created_at<(date_to+1)::timestamp at time zone 'Asia/Kuwait')
  and (status_filter is null or e.status=status_filter)
  and (coalesce(search_query,'')='' or e.receipt ilike '%'||left(search_query,120)||'%' or c.display_name ilike '%'||left(search_query,120)||'%'
   or c.phone ilike '%'||left(search_query,120)||'%' or c.email ilike '%'||left(search_query,120)||'%' or co.name ilike '%'||left(search_query,120)||'%')
 order by e.created_at desc,e.id desc limit least(greatest(coalesce(page_size,100),1),100) offset least(greatest(coalesce(page_offset,0),0),100000);
$$;
create function public.list_customers(search_query text default '',page_size integer default 100,page_offset integer default 0)
returns setof jsonb language sql stable security invoker set search_path='' as $$
 select to_jsonb(c)||jsonb_build_object('company',to_jsonb(co)) from public.customers c left join public.companies co on co.id=c.company_id
 where coalesce(search_query,'')='' or c.display_name ilike '%'||left(search_query,120)||'%' or c.phone ilike '%'||left(search_query,120)||'%'
  or c.email ilike '%'||left(search_query,120)||'%' or co.name ilike '%'||left(search_query,120)||'%'
 order by c.updated_at desc,c.id desc limit least(greatest(coalesce(page_size,100),1),100) offset least(greatest(coalesce(page_offset,0),0),100000);
$$;
create index customer_company on public.customers(company_id);
revoke all on function public.list_enquiries(date,date,public.enquiry_status,text,integer,integer),public.list_customers(text,integer,integer) from public,anon;
grant execute on function public.list_enquiries(date,date,public.enquiry_status,text,integer,integer),public.list_customers(text,integer,integer) to authenticated;
