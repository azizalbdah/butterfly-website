import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('public_export',Path(__file__).resolve().parents[1]/'scripts/build-public-preview.py')
export=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(export)

def test_key(role):
 payload=base64.urlsafe_b64encode(json.dumps({'role':role}).encode()).decode().rstrip('=')
 return 'header.'+payload+'.unit-test-signature'

class PublicExportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name);self.root=self.base/'checkout';self.root.mkdir()
  self.destination=self.base/'public';self.config=self.base/'private-config.json'
  self.config.write_text(json.dumps({'API_URL':'http://127.0.0.1:54321','ANON_KEY':test_key('anon'),'SERVICE_ROLE_KEY':'private-sentinel-never-export'}))

 def build(self):
  with patch.object(export,'ROOT',self.root),patch.object(export.subprocess,'check_output',side_effect=['commit-sha','']):export.build(self.destination,self.config)

 def test_only_public_files_and_public_bindings_cross_the_export_boundary(self):
  (self.root/'index.html').write_text('<h1>Public</h1>')
  (self.root/'assets').mkdir();(self.root/'assets/main.js').write_text('public')
  for relative in ['.env','.git/config','supabase/.temp/docker.env','staff/.env.local','assets/.env.private.js']:
   p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('private-sentinel-never-export')
  self.build()
  self.assertTrue((self.destination/'index.html').is_file())
  for p in self.destination.rglob('*'):
   if p.is_file():self.assertNotIn(b'private-sentinel-never-export',p.read_bytes())
  self.assertFalse((self.destination/'supabase').exists())
  self.assertFalse((self.destination/'staff').exists())

 def test_privileged_keys_are_rejected_before_creating_an_export(self):
  for key in ['sb_secret_private-unit-test',test_key('service_role')]:
   self.config.write_text(json.dumps({'API_URL':'http://127.0.0.1:54321','ANON_KEY':key}))
   with self.assertRaises(ValueError):self.build()
   self.assertFalse(self.destination.exists())

 def test_a_public_asset_symlink_cannot_export_a_private_target(self):
  (self.root/'assets').mkdir();(self.root/'assets/leak.json').symlink_to(self.config)
  with self.assertRaises(ValueError):self.build()
  self.assertFalse(self.destination.exists())

if __name__=='__main__':unittest.main()
