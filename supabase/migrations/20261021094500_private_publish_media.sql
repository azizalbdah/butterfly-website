-- Copying media precedes the publication transaction. Keep staged copies private:
-- a failed/concurrent publish must never make an unpublished draft photo public.
update storage.buckets set public=false where id='site-media';
drop policy site_media_read on storage.objects;
create policy site_media_editor_read on storage.objects for select to authenticated
 using(bucket_id='site-media' and public.app_can_manage_media());

create table public.site_published_media (
 name text primary key check(name~'^[a-f0-9]{64}\.(png|jpg|webp|avif)$'),
 first_revision_id uuid not null references public.site_revisions(id),
 created_at timestamptz not null default now()
);
alter table public.site_published_media enable row level security;
revoke all on public.site_published_media from anon,authenticated;
grant all on public.site_published_media to service_role;

create function public.site_record_published_media() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if NEW.kind='content' and NEW.operation='publication' then
  insert into public.site_published_media(name,first_revision_id)
   select substring(f.value->>'url' from 11),NEW.id from jsonb_each(NEW.payload->'fields') f
   join public.site_field_definitions d on d.id=f.key and d.kind='image'
   where f.value->>'url' like 'published:%' on conflict(name) do nothing;
 end if;
 return NEW;
end;
$$;
revoke all on function public.site_record_published_media() from public,anon,authenticated;
create trigger site_publication_media after insert on public.site_revisions
 for each row execute function public.site_record_published_media();

create function public.is_site_media_published(object_name text) returns boolean
language sql stable security definer set search_path='' as $$
 select object_name~'^[a-f0-9]{64}\.(png|jpg|webp|avif)$'
  and exists(select 1 from public.site_published_media p where p.name=object_name)
  and exists(select 1 from storage.objects o where o.bucket_id='site-media' and o.name=object_name);
$$;
revoke all on function public.is_site_media_published(text) from public;
grant execute on function public.is_site_media_published(text) to anon,authenticated,service_role;
