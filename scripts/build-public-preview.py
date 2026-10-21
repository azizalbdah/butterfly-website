#!/usr/bin/env python3
"""Export only public assets and public Supabase bindings into a fresh directory."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
FILES={'index.html','business.html','catering.html','links.html','favicon.ico','robots.txt','sitemap.xml','site.webmanifest'}
SUFFIXES={'.js','.mjs','.css','.json','.otf','.woff','.woff2','.png','.jpg','.jpeg','.webp','.avif','.svg','.ico'}

def build(destination,credentials):
 destination=Path(destination).resolve()
 if destination.exists() or destination.is_relative_to(ROOT):raise ValueError('Choose a fresh preview directory outside the checkout.')
 state=json.loads(Path(credentials).read_text())
 url=state.get('API_URL') or state.get('supabaseUrl')
 key=state.get('ANON_KEY') or state.get('publishableKey')
 parsed=urlsplit(url or '')
 if parsed.username or parsed.password or parsed.path not in ('','/') or not (parsed.scheme=='https' or (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1'))):raise ValueError('Use a verified HTTPS project endpoint or loopback development endpoint.')
 if not isinstance(key,str) or key.startswith('sb_secret_'):raise ValueError('A public browser key is required.')
 if not key.startswith('sb_publishable_'):
  try:
   part=key.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)))
   if claims.get('role')!='anon':raise ValueError()
  except Exception:raise ValueError('Privileged or invalid browser key rejected.') from None
 sources=[ROOT/name for name in FILES if (ROOT/name).is_file()]
 for directory in ('assets','fonts','images'):
  for source in (ROOT/directory).rglob('*'):
   if source.is_symlink():raise ValueError('Public exports reject symlinks.')
   if source.is_file() and not any(part.startswith('.') for part in source.relative_to(ROOT).parts) and source.suffix.lower() in SUFFIXES:sources.append(source)
 destination.mkdir(parents=True)
 for source in sources:
  output=destination/source.relative_to(ROOT);output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,output)
 config={'supabaseUrl':url.rstrip('/'),'publishableKey':key}
 (destination/'assets/runtime-config.js').write_text('window.BUTTERFLY_PUBLIC_CONFIG=Object.freeze('+json.dumps(config)+');\n')
 manifest={'commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
  'working_tree_clean':not bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True)),
  'production_deployed':False,'public_files':{str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}}
 (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('Public preview exported; browser configuration contains only the URL and public key.')

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',required=True);parser.add_argument('--credentials',default='/workspace/.butterfly-private/local-supabase.json');args=parser.parse_args()
 try:build(args.destination,args.credentials)
 except (OSError,ValueError):parser.exit(1,'Public preview export failed; check the destination and public configuration. No secrets were printed.\n')
