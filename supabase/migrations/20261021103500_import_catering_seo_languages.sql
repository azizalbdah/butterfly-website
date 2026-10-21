-- Preserve the external calculator's original English/Arabic SEO title.
-- Append a corrected import revision; do not rewrite existing revision history.
do $$
declare original jsonb; corrected jsonb;
begin
 select payload into original from public.site_templates where kind='content' for update;
 corrected:=jsonb_set(original,array['fields','catering-seo-006'],$title${"en": "Butterfly Catering | Hospitality, weddings & coffee", "ar": "كيترنق بترفلاي | ضيافة وأعراس وقهوة"}$title$::jsonb);
 update public.site_templates set payload=corrected where kind='content';
 insert into public.site_revisions(id,kind,operation,payload)
  values('10000000-0000-4000-8000-000000000003','content','seed',corrected);
 update public.site_document_heads h set
  draft_id=case when (select payload from public.site_revisions where id=h.draft_id)=original then '10000000-0000-4000-8000-000000000003'::uuid else h.draft_id end,
  published_id=case when (select payload from public.site_revisions where id=h.published_id)=original then '10000000-0000-4000-8000-000000000003'::uuid else h.published_id end,
  updated_at=now() where h.kind='content';
 insert into public.audit_log(action,entity_type,entity_id,changes)
  values('site.import-seo-correction','site_revision','10000000-0000-4000-8000-000000000003',jsonb_build_object('field','catering-seo-006','source','preserved calculator language handler'));
end;
$$;
