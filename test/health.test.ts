import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startTestApp } from './helpers/testApp.ts';
import type { TestApp } from './helpers/testApp.ts';

let t: TestApp;
before(async () => { t = await startTestApp(); });
after(async () => { await t.close(); });

test('GET /api/health responde ok con db up', async () => {
  const r = await t.request('GET', '/api/health');
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
  assert.equal(r.body.db, 'up');
});

test('ruta inexistente devuelve 404 con formato de error único', async () => {
  const r = await t.request('GET', '/api/nada');
  assert.equal(r.status, 404);
  assert.equal(r.body.error.code, 'NOT_FOUND');
});
