-- Stage B: invitation-only staff membership, server-enforced roles/MFA and audit.
-- Additive migration. Bootstrap the first administrator through a trusted operator,
-- never through public signup or editable Auth user metadata.

create type public.staff_role as enum ('admin', 'sales', 'marketing');

create table public.staff_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 100),
  role public.staff_role not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.audit_log (
  id uuid primary key default gen_random_uuid(),
  -- Preserve actor attribution even if an operator later deletes the Auth user.
  -- Audit identifiers deliberately do not cascade or null with account removal.
  actor_user_id uuid,
  action text not null,
  entity_type text not null,
  entity_id uuid not null,
  changes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index audit_log_created_at_idx on public.audit_log (created_at desc);
create index audit_log_entity_idx on public.audit_log (entity_type, entity_id, created_at desc);

revoke create on schema public from public, anon, authenticated;
alter table public.staff_members enable row level security;
alter table public.audit_log enable row level security;

-- SECURITY DEFINER functions have a fixed empty search_path and explicit object
-- qualification, avoiding recursive staff RLS and caller-controlled object lookup.
-- GoTrue removes a session on signout/revocation. Check its live row so that an
-- otherwise unexpired captured access JWT cannot keep using staff permissions.
create function public.app_session_active()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists (
    select 1 from auth.sessions s
    where s.id::text = auth.jwt() ->> 'session_id'
      and s.user_id = auth.uid()
      and (s.not_after is null or s.not_after > now())
  );
$$;

create function public.app_staff_role()
returns public.staff_role
language sql stable security definer set search_path = ''
as $$
  select m.role from public.staff_members m
  where m.user_id = auth.uid() and m.active and public.app_session_active();
$$;

create function public.app_is_admin()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select coalesce(
    public.app_staff_role() = 'admin'::public.staff_role
    and auth.jwt() ->> 'aal' = 'aal2'
    -- Unenrolling a factor can downgrade a live session without deleting it.
    -- Old captured aal2 JWTs must lose administrator access immediately too.
    and exists (
      select 1 from auth.sessions s
      where s.id::text = auth.jwt() ->> 'session_id'
        and s.user_id = auth.uid() and s.aal = 'aal2'
    ),
    false
  );
$$;

create function public.app_can_manage_media()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select coalesce(
    public.app_staff_role() = 'marketing'::public.staff_role
    or public.app_is_admin(),
    false
  );
$$;

revoke all on function public.app_session_active() from public, anon;
revoke all on function public.app_staff_role() from public, anon;
revoke all on function public.app_is_admin() from public, anon;
revoke all on function public.app_can_manage_media() from public, anon;
grant execute on function public.app_session_active() to authenticated, service_role;
grant execute on function public.app_staff_role() to authenticated, service_role;
grant execute on function public.app_is_admin() to authenticated, service_role;
grant execute on function public.app_can_manage_media() to authenticated, service_role;

-- A member may discover only their own active membership at aal1 so that the UI
-- can require MFA. All administrator list/audit/privileged access requires aal2.
create policy staff_read_own_or_admin on public.staff_members
for select to authenticated
using ((user_id = auth.uid() and active and public.app_session_active()) or public.app_is_admin());

create policy audit_read_admin on public.audit_log
for select to authenticated using (public.app_is_admin());

revoke all on public.staff_members from anon, authenticated;
revoke all on public.audit_log from anon, authenticated;
grant select on public.staff_members, public.audit_log to authenticated;
grant all on public.staff_members, public.audit_log to service_role;

create function public.staff_record_audit()
returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.audit_log (actor_user_id, action, entity_type, entity_id, changes)
  values (
    auth.uid(),
    'staff.' || lower(TG_OP),
    'staff_member',
    coalesce(NEW.user_id, OLD.user_id),
    jsonb_build_object(
      'before', case when TG_OP <> 'INSERT' then to_jsonb(OLD) else null end,
      'after', case when TG_OP <> 'DELETE' then to_jsonb(NEW) else null end
    )
  );
  return coalesce(NEW, OLD);
end;
$$;
revoke all on function public.staff_record_audit() from public, anon, authenticated;

create trigger staff_audit_changes
after insert or update or delete on public.staff_members
for each row execute function public.staff_record_audit();

create function public.update_staff_member(
  target_user_id uuid,
  new_role public.staff_role,
  new_active boolean,
  new_display_name text
)
returns public.staff_members
language plpgsql security definer set search_path = ''
as $$
declare result public.staff_members;
begin
  if not public.app_is_admin() then
    raise exception 'Administrator MFA is required.' using errcode = '42501';
  end if;
  if target_user_id = auth.uid() then
    raise exception 'Use another administrator to change your membership.' using errcode = '42501';
  end if;
  if new_role is null or new_active is null or new_display_name is null
     or char_length(btrim(new_display_name)) not between 1 and 100 then
    raise exception 'A valid role, status and display name are required.' using errcode = '22023';
  end if;
  update public.staff_members
  set role = new_role, active = new_active, display_name = btrim(new_display_name), updated_at = now()
  where user_id = target_user_id
  returning * into result;
  if not found then
    raise exception 'Staff member not found.' using errcode = 'P0002';
  end if;
  return result;
end;
$$;
revoke all on function public.update_staff_member(uuid, public.staff_role, boolean, text) from public, anon;
grant execute on function public.update_staff_member(uuid, public.staff_role, boolean, text) to authenticated;

-- Called with the initiating admin's JWT after server-side Auth invitation. This
-- preserves the verified human actor in the audit trigger. A direct client call
-- still requires administrator MFA and an actual Auth-admin-invited target.
create function public.register_staff_invitation(
  target_user_id uuid,
  new_role public.staff_role,
  new_display_name text
)
returns public.staff_members
language plpgsql security definer set search_path = ''
as $$
declare result public.staff_members;
begin
  if not public.app_is_admin() then
    raise exception 'Administrator MFA is required.' using errcode = '42501';
  end if;
  if target_user_id = auth.uid() then
    raise exception 'Cannot replace your own membership.' using errcode = '42501';
  end if;
  if new_role is null or new_display_name is null
     or char_length(btrim(new_display_name)) not between 1 and 100 then
    raise exception 'A valid role and display name are required.' using errcode = '22023';
  end if;
  if not exists(select 1 from auth.users u where u.id = target_user_id and u.invited_at is not null) then
    raise exception 'An Auth administrator invitation is required.' using errcode = '42501';
  end if;
  insert into public.staff_members (user_id, role, display_name)
  values (target_user_id, new_role, btrim(new_display_name)) returning * into result;
  return result;
end;
$$;
revoke all on function public.register_staff_invitation(uuid, public.staff_role, text) from public, anon;
grant execute on function public.register_staff_invitation(uuid, public.staff_role, text) to authenticated;

-- Staff media is private. Marketing may prepare media; only MFA administrators
-- can access it in their administrator role. Sales has no access to this bucket.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('staff-media', 'staff-media', false, 10485760,
        array['image/jpeg', 'image/png', 'image/webp', 'image/avif']);

create policy staff_media_select on storage.objects
for select to authenticated
using (bucket_id = 'staff-media' and public.app_can_manage_media());
create policy staff_media_insert on storage.objects
for insert to authenticated
with check (bucket_id = 'staff-media' and public.app_can_manage_media());
create policy staff_media_update on storage.objects
for update to authenticated
using (bucket_id = 'staff-media' and public.app_can_manage_media())
with check (bucket_id = 'staff-media' and public.app_can_manage_media());
create policy staff_media_delete on storage.objects
for delete to authenticated
using (bucket_id = 'staff-media' and public.app_can_manage_media());
