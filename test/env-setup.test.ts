import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, copyFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { parseEnv } from '../src/config/parse.ts';
import { setup } from '../scripts/setup.ts';

test('setup crea .env con claves aleatorias y una 2ª ejecución no lo cambia', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'flowclic-setup-'));
  await copyFile('.env.example', path.join(dir, '.env.example'));
  assert.equal(await setup(dir), 'created');
  const first = await readFile(path.join(dir, '.env'), 'utf8');
  const key = /^APP_ENCRYPTION_KEY=(.+)$/m.exec(first)?.[1] ?? '';
  assert.equal(Buffer.from(key, 'base64').length, 32);
  assert.match(first, /^SESSION_SECRET=.{40,}$/m);
  assert.equal(await setup(dir), 'exists');
  assert.equal(await readFile(path.join(dir, '.env'), 'utf8'), first);
  await rm(dir, { recursive: true, force: true });
});

test('.env.example no contiene secretos reales', async () => {
  const ex = await readFile('.env.example', 'utf8');
  assert.match(ex, /^APP_ENCRYPTION_KEY=$/m);
  assert.match(ex, /^SESSION_SECRET=$/m);
  assert.match(ex, /^TURSO_AUTH_TOKEN=$/m);
});

test('en producción exige claves; en desarrollo no', () => {
  const base = { TURSO_DATABASE_URL: 'file:x.db' };
  assert.doesNotThrow(() => parseEnv(base));
  assert.throws(() => parseEnv({ ...base, NODE_ENV: 'production' }), /obligatoria en producción/);
  const k = Buffer.alloc(32, 1).toString('base64');
  assert.doesNotThrow(() => parseEnv({ ...base, NODE_ENV: 'production', APP_ENCRYPTION_KEY: k, SESSION_SECRET: k }));
  assert.throws(() => parseEnv({ ...base, APP_ENCRYPTION_KEY: 'corta' }), /32 bytes/);
});

test('variables vacías equivalen a no definidas', () => {
  const env = parseEnv({ TURSO_DATABASE_URL: 'file:x.db', TURSO_AUTH_TOKEN: '', SESSION_IDLE_MINUTES: '' });
  assert.equal(env.TURSO_AUTH_TOKEN, undefined);
  assert.equal(env.SESSION_IDLE_MINUTES, 30);
});
