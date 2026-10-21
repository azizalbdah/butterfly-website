-- Report optimistic concurrency rejection as HTTP 409 through PostgREST.
-- Explicitly deny NULL role results for uninvited/inactive/revoked sessions.
create or replace function public.save_site_draft(document_kind text, new_payload jsonb, expected_draft_id uuid)
returns public.site_revisions language plpgsql security definer set search_path='' as $$
declare head public.site_document_heads; revision public.site_revisions;
begin
 if not coalesce(public.app_is_admin() or (document_kind='content' and public.app_staff_role()='marketing'),false) then
  raise exception 'Editor permission is required.' using errcode='42501'; end if;
 select * into head from public.site_document_heads where kind=document_kind for update;
 if not found then raise exception 'Document not found.' using errcode='22023'; end if;
 if head.draft_id is distinct from expected_draft_id then raise exception 'This draft changed. Reload before saving.' using errcode='PT409'; end if;
 if not coalesce(public.app_site_payload_valid(document_kind,new_payload),false) then raise exception 'Document validation failed.' using errcode='22023'; end if;
 insert into public.site_revisions(kind,parent_id,operation,payload,created_by)
  values(document_kind,head.draft_id,'draft',new_payload,auth.uid()) returning * into revision;
 update public.site_document_heads set draft_id=revision.id,updated_at=now() where kind=document_kind;
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes)
  values(auth.uid(),'site.draft','site_revision',revision.id,jsonb_build_object('kind',document_kind,'previous_draft',head.draft_id));
 return revision;
end;
$$;


create or replace function public.publish_site_document(document_kind text, revision_id uuid, expected_published_id uuid, media_mappings jsonb default '{}')
returns public.site_revisions language plpgsql security definer set search_path='' as $$
declare head public.site_document_heads; draft public.site_revisions; revision public.site_revisions; payload jsonb; field record; mapped text;
begin
 if not public.app_is_admin() then raise exception 'Administrator MFA is required.' using errcode='42501'; end if;
 select * into head from public.site_document_heads where kind=document_kind for update;
 if not found then raise exception 'Document not found.' using errcode='22023'; end if;
 if head.draft_id is distinct from revision_id or head.published_id is distinct from expected_published_id then
  raise exception 'Document changed. Reload before publishing.' using errcode='PT409'; end if;
 select * into draft from public.site_revisions where id=revision_id and kind=document_kind;
 payload:=draft.payload;
 if document_kind='content' then
  for field in select f.key,f.value from jsonb_each(payload->'fields') f join public.site_field_definitions d on d.id=f.key and d.kind='image' loop
   if field.value->>'url' like 'private:%' then
    mapped:=media_mappings->>(field.value->>'url');
    if mapped is null or mapped!~'^published:[a-f0-9]{64}\.(png|jpg|webp|avif)$' then raise exception 'Publish media before this draft.' using errcode='22023'; end if;
    payload:=jsonb_set(payload,array['fields',field.key,'url'],to_jsonb(mapped));
   end if;
  end loop;
 end if;
 if not public.app_site_payload_valid(document_kind,payload) then raise exception 'Publication validation failed.' using errcode='22023'; end if;
 insert into public.site_revisions(kind,parent_id,operation,payload,created_by)
  values(document_kind,revision_id,'publication',payload,auth.uid()) returning * into revision;
 update public.site_document_heads set published_id=revision.id,updated_at=now() where kind=document_kind;
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes)
  values(auth.uid(),'site.publish','site_revision',revision.id,jsonb_build_object('kind',document_kind,'previous_publication',head.published_id,'draft',revision_id));
 return revision;
end;
$$;