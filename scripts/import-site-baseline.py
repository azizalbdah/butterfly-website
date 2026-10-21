#!/usr/bin/env python3
"""Import designated fields from the preserved public release, never from drafts."""
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
        source = self.source
        for offset,extra in sorted(self.edits,reverse=True):
            source = source[:offset]+extra+source[offset:]
        source = source.replace('<head>', '<head><script defer src="assets/runtime-config.js"></script><script defer src="assets/site-client.js"></script>',1)
        # Editable content must never enter an HTML execution sink.
        source = source.replace('if (t) el.innerHTML = t;', "if (t) el.replaceChildren(...t.split(/<br\\s*\\/?>|\\n/g).flatMap((part,i)=>i?[document.createElement('br'),document.createTextNode(part)]:[document.createTextNode(part)]));")
        return source


def main():
    definitions, fields = [], {}
    for page in ('index','business','catering','links'):
        source = subprocess.check_output(['git','show',BASELINE+':'+page+'.html'],cwd=ROOT,text=True)
        parser = Importer(page,source)
        parser.feed(source)
        updated = parser.result()
        (ROOT/(page+'.html')).write_text(updated)
        definitions.extend(parser.definitions)
        fields.update(parser.values)
    output = {'baseline_commit':BASELINE,'definitions':definitions,'content':{'schema':1,'fields':fields}}
    (ROOT/'assets/content-baseline.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print('Imported',len(definitions),'designated bilingual, image, link and SEO fields from the preserved release.')


if __name__ == '__main__':
    main()
