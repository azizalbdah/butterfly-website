#!/usr/bin/env python3
"""Import designated fields from the preserved public release, never from drafts."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd'


class Importer(HTMLParser):
    def __init__(self, page, source):
        super().__init__(convert_charrefs=True)
        self.page, self.source = page, source
        self.lines = [0]
        for match in re.finditer('\n', source):
            self.lines.append(match.end())
        self.edits, self.definitions, self.values = [], [], {}
        self.hidden = 0
        self.title = None

    def add(self, kind, attrs, value, label):
        field_id = f'{self.page}-{kind}-{len(self.definitions)+1:03}'
        self.definitions.append({'id':field_id, 'page':self.page, 'kind':kind, 'label':label[:100]})
        self.values[field_id] = value
        return f' data-site-{kind}="{field_id}"'

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag in ('script','noscript'):
            self.hidden += 1
        if self.hidden:
            return
        extra = ''
        if 'data-en' in attrs:
            values = {lang:re.sub(r'<br\s*/?>', '\n', attrs.get('data-'+lang,'')) for lang in ('en','ar')}
            extra += self.add('text', attrs, values, values['en'])
        if tag == 'a' and attrs.get('href') and not attrs['href'].startswith('javascript:'):
            extra += self.add('link', attrs, {'url':attrs['href']}, attrs.get('data-en') or attrs.get('aria-label') or attrs['href'])
        if tag == 'img' and attrs.get('src','').startswith('images/'):
            src = attrs['src']
            # Preserve the image actually displayed by an approved fallback.
            if not (ROOT/src).is_file():
                fallback = re.search(r"this\.src=['\"]([^'\"]+)", attrs.get('onerror',''))
                if fallback and (ROOT/fallback[1]).is_file():
                    src = fallback[1]
            extra += self.add('image', attrs, {'url':src,'alt_en':attrs.get('data-alt-en',attrs.get('alt','')),'alt_ar':attrs.get('data-alt-ar',attrs.get('alt',''))}, attrs.get('alt') or src)
        if tag == 'title':
            self.title = self.add('seo', attrs, {'en':'','ar':''}, 'Page title')
            extra += self.title
        if tag == 'meta' and (attrs.get('name') in ('description','twitter:title','twitter:description') or attrs.get('property') in ('og:title','og:description')):
            extra += self.add('seo', attrs, {'en':attrs.get('content',''),'ar':attrs.get('content','')}, attrs.get('name') or attrs['property'])
        if extra:
            row,column = self.getpos()
            offset = self.lines[row-1]+column
            raw = self.get_starttag_text()
            end = offset+len(raw)-1
            if raw.endswith('/>'):
                end -= 1
            self.edits.append((end,extra))

    def handle_endtag(self, tag):
        if tag in ('script','noscript'):
            self.hidden = max(0,self.hidden-1)

    def result(self):
        # Titles are present in the original language handlers.
        title = re.search(r'<title>(.*?)</title>',self.source,re.S)[1]
        match = re.search(r"document\.title\s*=\s*lang\s*===?\s*['\"]ar['\"]\s*\?\s*(['\"])(.*?)\1\s*:\s*(['\"])(.*?)\3",self.source,re.S)
        field_id = next(d['id'] for d in self.definitions if d['kind']=='seo' and d['label']=='Page title')
        self.values[field_id] = {'en':match[4] if match else title,'ar':match[2] if match else title}
        if self.page=='catering':
            script=subprocess.check_output(['git','show',BASELINE+':assets/catering-configurator.js'],cwd=ROOT,text=True)
            translated=re.search(r"document\.title=tr\('([^']*)','([^']*)'\)",script)
            if translated:self.values[field_id]={'en':translated[1],'ar':translated[2]}
        source = self.source
        for offset,extra in sorted(self.edits,reverse=True):
            source = source[:offset]+extra+source[offset:]
        source = source.replace('<head>', '<head><script defer src="assets/runtime-config.js"></script><script defer src="assets/site-client.js"></script>',1)
        # Editable content must never enter an HTML execution sink.
        source = source.replace('if (t) el.innerHTML = t;', "if (t) el.replaceChildren(...t.split(/<br\\s*\\/?>|\\n/g).flatMap((part,i)=>i?[document.createElement('br'),document.createTextNode(part)]:[document.createTextNode(part)]));")
        return source


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--destination',type=Path,help='Fresh directory for a reviewable regeneration; default checks the original checkout.')
    args=cli.parse_args();destination=args.destination.resolve() if args.destination else ROOT
    if args.destination and destination.exists():cli.error('Choose a fresh destination.')
    definitions, fields, pages = [], {}, {}
    for page in ('index','business','catering','links'):
        source = subprocess.check_output(['git','show',BASELINE+':'+page+'.html'],cwd=ROOT,text=True)
        parser = Importer(page,source)
        parser.feed(source)
        updated = parser.result()
        target=destination/(page+'.html')
        if destination==ROOT and target.exists() and target.read_text() not in (source,updated):
            cli.error('Public HTML has later changes. Regenerate into a fresh destination and review individual changes.')
        pages[page+'.html']=updated
        definitions.extend(parser.definitions)
        fields.update(parser.values)
    output = {'baseline_commit':BASELINE,'content_seed_revision':'10000000-0000-4000-8000-000000000003','catalogue_seed_revision':'10000000-0000-4000-8000-000000000002','definitions':definitions,'content':{'schema':1,'fields':fields}}
    payload=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
    target=destination/'assets/content-baseline.json'
    if destination==ROOT and target.exists() and target.read_text()!=payload:cli.error('Baseline metadata differs. Regenerate into a fresh destination for review.')
    (destination/'assets').mkdir(parents=True,exist_ok=True)
    for name,html in pages.items():(destination/name).write_text(html)
    target.write_text(payload)
    print('Imported',len(definitions),'designated bilingual, image, link and SEO fields from the preserved release.')


if __name__ == '__main__':
    main()
