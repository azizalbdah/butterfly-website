-- Explicitly deny NULL role results for uninvited/inactive/revoked sessions.
create or replace function public.save_site_draft(document_kind text, new_payload jsonb, expected_draft_id uuid)
returns public.site_revisions language plpgsql security definer set search_path='' as $$
declare head public.site_document_heads; revision public.site_revisions;
begin
 if not coalesce(public.app_is_admin() or (document_kind='content' and public.app_staff_role()='marketing'),false) then
  raise exception 'Editor permission is required.' using errcode='42501'; end if;
 select * into head from public.site_document_heads where kind=document_kind for update;
 if not found then raise exception 'Document not found.' using errcode='22023'; end if;
 if head.draft_id is distinct from expected_draft_id then raise exception 'This draft changed. Reload before saving.' using errcode='40001'; end if;
 if not coalesce(public.app_site_payload_valid(document_kind,new_payload),false) then raise exception 'Document validation failed.' using errcode='22023'; end if;
 insert into public.site_revisions(kind,parent_id,operation,payload,created_by)
  values(document_kind,head.draft_id,'draft',new_payload,auth.uid()) returning * into revision;
 update public.site_document_heads set draft_id=revision.id,updated_at=now() where kind=document_kind;
 insert into public.audit_log(actor_user_id,action,entity_type,entity_id,changes)
  values(auth.uid(),'site.draft','site_revision',revision.id,jsonb_build_object('kind',document_kind,'previous_draft',head.draft_id));
 return revision;
end;
$$;
