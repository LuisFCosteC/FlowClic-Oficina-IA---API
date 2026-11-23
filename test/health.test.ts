import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startTestApp } from './helpers/testApp.ts';
import type { TestApp } from './helpers/testApp.ts';

let t: TestApp;
before(async () => { t = await startTestApp(); });
after(async () => { await t.close(); });

test('GET /api/health responde solo {ok} sin sesión', async () => {
  const r = await t.request('GET', '/api/health');
  assert.equal(r.status, 200);
  assert.equal(r.body.ok, true);
});

test('ruta inexistente devuelve 404 con formato de error único', async () => {
  const r = await t.request('GET', '/api/nada');
  assert.equal(r.status, 404);
  assert.equal(r.body.error.code, 'NOT_FOUND');
});

test('cabeceras de seguridad presentes y sin X-Powered-By', async () => {
  const res = await fetch(t.baseUrl + '/api/health');
  assert.equal(res.headers.get('x-powered-by'), null);
  assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(res.headers.get('x-frame-options'), 'DENY');
  assert.equal(res.headers.get('referrer-policy'), 'no-referrer');
  assert.match(res.headers.get('content-security-policy') ?? '', /default-src 'none'/);
  assert.ok(res.headers.get('x-request-id'));
  assert.deepEqual(await res.json(), { ok: true });
});

test('body de 200 kB devuelve 413 en JSON', async () => {
  const r = await t.request('POST', '/api/health', { x: 'a'.repeat(200_000) });
  assert.equal(r.status, 413);
  assert.equal(r.body.error.code, 'PAYLOAD_TOO_LARGE');
});
