// Build only the lockfile-pinned SDK and Edge handler; never load staff app/env files.
import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const staff = resolve(root, 'staff');
const folder = resolve(root, 'supabase/functions/.env.local-preview');
const sdkVersion = '2.118.0';
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

try {
  const lockBytes = await readFile(resolve(staff, 'package-lock.json'));
  const lock = JSON.parse(lockBytes);
  const pinned = lock.packages['node_modules/@supabase/supabase-js'];
  const installed = JSON.parse(await readFile(resolve(staff, 'node_modules/@supabase/supabase-js/package.json')));
  if (pinned.version !== sdkVersion || installed.version !== sdkVersion || !pinned.integrity) {
    throw new Error('SDK must match its verified, pinned npm lockfile.');
  }
  const { build } = await import(pathToFileURL(resolve(staff, 'node_modules/rolldown/dist/index.mjs')));
  await mkdir(folder, { recursive: true, mode: 0o700 });
  const sdkEntry = resolve(staff, 'node_modules/@supabase/supabase-js/dist/index.mjs');
  const bundle = resolve(folder, 'supabase-js.mjs');
  const virtualEntry = '\0butterfly-local-sdk-only';
  const output = await build({
    input: virtualEntry,
    cwd: staff,
    platform: 'browser',
    plugins: [{
      name: 'butterfly-sdk-only',
      resolveId(id) { if (id === virtualEntry) return virtualEntry; },
      load(id) { if (id === virtualEntry) return `export { createClient } from ${JSON.stringify(sdkEntry)};`; },
    }],
    output: { file: bundle, format: 'esm', codeSplitting: false, sourcemap: false },
  });
  if (output.output.length !== 1 || output.output[0].type !== 'chunk' ||
      output.output[0].imports.length || output.output[0].dynamicImports.length) {
    throw new Error('SDK bundle must be self-contained.');
  }
  const bundleBytes = await readFile(bundle);
  const functions = {};
  for (const name of ['invite-staff','publish-site','site-media']) {
    const source=resolve(root,'supabase/functions',name,'index.ts');
    const functionFolder=resolve(folder,name);
    const artifact=resolve(functionFolder,'index.js');
    await mkdir(functionFolder,{recursive:true,mode:0o700});
    const built=await build({input:source,cwd:staff,platform:'browser',
      resolve:{alias:{'@supabase/supabase-js':sdkEntry}},
      output:{file:artifact,format:'esm',codeSplitting:false,sourcemap:false}});
    if(built.output.length!==1||built.output[0].type!=='chunk'||built.output[0].imports.length||built.output[0].dynamicImports.length)throw new Error('Edge bundles must be self-contained.');
    functions[name]={source_sha256:sha256(await readFile(source)),bundle_sha256:sha256(await readFile(artifact))};
  }
  const metadata = {
    sdk: '@supabase/supabase-js', version: sdkVersion,
    npm_integrity: pinned.integrity,
    lockfile_sha256: sha256(lockBytes), bundle_sha256: sha256(bundleBytes),
    functions,
    scope: 'SDK plus exact Edge handler only; production source map pins the npm dependency.',
  };
  await writeFile(resolve(folder, 'sdk-metadata.json'), JSON.stringify(metadata, null, 2) + '\n', { mode: 0o600 });
  await writeFile(resolve(folder, 'import_map.json'), JSON.stringify({
    imports: { '@supabase/supabase-js': pathToFileURL(bundle).href },
  }, null, 2) + '\n', { mode: 0o600 });
  await writeFile(resolve(folder, 'compiled-import-map.json'), '{"imports":{}}\n', { mode: 0o600 });
  console.log(`Verified SDK and actual Edge-handler bundles ${sdkVersion}; source/lock/artifact SHA256 recorded.`);
} catch {
  console.error('Local SDK bundle failed. Install staff dependencies with npm ci and preserve normal TLS/integrity verification.');
  process.exitCode = 1;
}
