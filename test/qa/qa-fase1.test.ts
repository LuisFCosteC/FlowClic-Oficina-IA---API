// Pruebas de QA (tareas T10–T14, T20–T24, T30 y S01). Solo node:test + fetch. No usan local.db.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import type { AddressInfo } from 'node:net';
import type { Server } from 'node:http';
import express from 'express';
import { z } from 'zod';
import { startTestApp } from '../helpers/testApp.ts';
import type { TestApp } from '../helpers/testApp.ts';
import { createDb } from '../../src/db/client.ts';
import { migrate } from '../../src/db/migrate.ts';
import { seed } from '../../seeds/seed.ts';
import { errorHandler, notFoundHandler } from '../../src/middleware/errors.ts';

const SRC = path.resolve(import.meta.dirname, '../../src');

async function tmpDir(): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), 'flowclic-qa-'));
}

// ───────── T10 · client.ts ─────────
test('T10: createDb con file: ejecuta SELECT 1 con token vacío y sin token', async () => {
  const dir = await tmpDir();
  try {
    const url = `file:${path.join(dir, 'x.db').split(path.sep).join('/')}`;
    for (const cfg of [{ url, authToken: '' }, { url, authToken: undefined }, { url, authToken: '   ' }]) {
      const db = createDb(cfg);
      const r = await db.execute('SELECT 1 AS n');
      assert.equal(Number(r.rows[0]?.n), 1);
      db.close();
    }
  } finally {
    await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }).catch(() => {});
  }
});

// ───────── T11 · migrate.ts ─────────
test('T11: 1ª ejecución aplica todo, 2ª no aplica nada', async () => {
  const dir = await tmpDir();
  try {
    const db = createDb({ url: `file:${path.join(dir, 'm.db').split(path.sep).join('/')}` });
    const first = await migrate(db);
    assert.deepEqual(first.applied, ['001_init.sql']);
    const second = await migrate(db);
    assert.deepEqual(second.applied, []);
    const v = await db.execute('SELECT COUNT(*) AS n FROM schema_migrations');
    assert.equal(Number(v.rows[0]?.n), 1);
    db.close();
  } finally {
    await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }).catch(() => {});
  }
});

test('T11: migración con SQL roto no se registra y no deja tablas parciales', async () => {
  const dir = await tmpDir();
  const migDir = path.join(dir, 'migs');
  try {
    await mkdir(migDir);
    await writeFile(path.join(migDir, '001_ok.sql'), 'CREATE TABLE ok_t (x INTEGER);');
    await writeFile(
      path.join(migDir, '002_broken.sql'),
      'CREATE TABLE partial_t (x INTEGER); INSERT INTO tabla_que_no_existe VALUES (1);',
    );
    const db = createDb({ url: `file:${path.join(dir, 'b.db').split(path.sep).join('/')}` });
    await assert.rejects(migrate(db, migDir), /002_broken\.sql/);
    const reg = await db.execute('SELECT version FROM schema_migrations ORDER BY version');
    assert.deepEqual(reg.rows.map((r) => Number(r.version)), [1], '002 no debe quedar registrada');
    const tables = await db.execute(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='partial_t'",
    );
    assert.equal(tables.rows.length, 0, 'partial_t no debe existir (rollback)');
    db.close();
  } finally {
    await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }).catch(() => {});
  }
});

// ───────── T12 · 001_init.sql (CHECKs e índices) ─────────
let t: TestApp;
before(async () => { t = await startTestApp({ seed: false }); await seed(t.db); });
after(async () => { await t.close(); });

test('T12: status inválido en agents/tickets/approvals falla por CHECK', async () => {
  await assert.rejects(
    t.db.execute(`INSERT INTO agents (id,name,character,role,status,created_at,updated_at)
                  VALUES ('x1','X','X','X','FOO','now','now')`),
    /CHECK/,
  );
  await assert.rejects(
    t.db.execute(`INSERT INTO tickets (id,title,status,created_at,updated_at)
                  VALUES ('tx1','X','FOO','now','now')`),
    /CHECK/,
  );
  await assert.rejects(
    t.db.execute(`INSERT INTO approvals (id,title,status,requested_at)
                  VALUES ('ax1','X','FOO','now')`),
    /CHECK/,
  );
});

test('T12: 2ª aprobación PENDING para el mismo ticket falla por índice único', async () => {
  // seed-ticket-4 ya tiene la PENDING sembrada.
  await assert.rejects(
    t.db.execute(`INSERT INTO approvals (id,ticket_id,title,status,requested_at)
                  VALUES ('ax2','seed-ticket-4','Otra','PENDING','now')`),
    /UNIQUE/,
  );
});

test('T12: una aprobación no PENDING para el mismo ticket sí se permite', async () => {
  await t.db.execute(`INSERT INTO approvals (id,ticket_id,title,status,requested_at)
                      VALUES ('ax3','seed-ticket-4','Histórica','APPROVED','now')`);
});

// ───────── T13 · seed.ts idempotente ─────────
test('T13: ejecutar la semilla 2 veces deja 4 agentes y Sheldon isCto=1', async () => {
  await seed(t.db);
  await seed(t.db);
  const n = await t.db.execute('SELECT COUNT(*) AS n FROM agents');
  assert.equal(Number(n.rows[0]?.n), 4);
  const sheldon = await t.db.execute("SELECT is_cto FROM agents WHERE id='sheldon'");
  assert.equal(Number(sheldon.rows[0]?.is_cto), 1);
  const ids = (await t.db.execute('SELECT id FROM agents ORDER BY id')).rows.map((r) => r.id);
  assert.deepEqual(ids, ['leonard', 'penny', 'raj', 'sheldon']);
});

test('T13: semilla crea 4 tickets (uno por columna activa), 1 PENDING y 1 nota', async () => {
  const statuses = (await t.db.execute('SELECT status FROM tickets ORDER BY status')).rows.map((r) => r.status);
  assert.deepEqual(statuses, ['AWAITING_APPROVAL', 'BACKLOG', 'IN_PROGRESS', 'REVIEW']);
  const pending = await t.db.execute("SELECT COUNT(*) AS n FROM approvals WHERE status='PENDING'");
  assert.equal(Number(pending.rows[0]?.n), 1);
  const mem = await t.db.execute('SELECT COUNT(*) AS n FROM project_memory');
  assert.equal(Number(mem.rows[0]?.n), 1);
});

// ───────── T20 · app.ts / health / CORS ─────────
test('T20: GET /api/health → 200 {ok:true}', async () => {
  const r = await t.request('GET', '/api/health');
  assert.equal(r.status, 200);
  assert.deepEqual(r.body, { ok: true });
});

test('T20: CORS: origen permitido recibe ACAO; origen ajeno no recibe ACAO', async () => {
  const ok = await fetch(t.baseUrl + '/api/health', { headers: { Origin: 'http://localhost:3000' } });
  assert.equal(ok.headers.get('access-control-allow-origin'), 'http://localhost:3000');
  // cors devuelve siempre el origen configurado: nunca refleja el origen ajeno, así el navegador bloquea.
  const bad = await fetch(t.baseUrl + '/api/health', { headers: { Origin: 'http://evil.example' } });
  assert.notEqual(bad.headers.get('access-control-allow-origin'), 'http://evil.example');
  assert.equal(bad.headers.get('access-control-allow-origin'), 'http://localhost:3000');
  const pre = await fetch(t.baseUrl + '/api/health', {
    method: 'OPTIONS',
    headers: { Origin: 'http://evil.example', 'Access-Control-Request-Method': 'POST' },
  });
  assert.notEqual(pre.headers.get('access-control-allow-origin'), 'http://evil.example');
});

// ───────── T21 · errores ─────────
test('T21: JSON mal formado → 400 con forma {error:{code,message,details}}', async () => {
  const res = await fetch(t.baseUrl + '/api/health', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{"a":',
  });
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.deepEqual(Object.keys(body), ['error']);
  assert.deepEqual(Object.keys(body.error).sort(), ['code', 'details', 'message']);
  assert.equal(body.error.code, 'VALIDATION_ERROR');
});

test('T21: ruta inexistente → 404 JSON con NOT_FOUND', async () => {
  const r = await t.request('GET', '/api/no-existe');
  assert.equal(r.status, 404);
  assert.equal(r.body.error.code, 'NOT_FOUND');
  assert.ok(Array.isArray(r.body.error.details));
});

test('T21: zod → 400 con details; error genérico → 500 sin stack ni detalles internos', async () => {
  const app = express();
  app.use(express.json());
  app.post('/z', (req, res) => {
    z.object({ a: z.string() }).parse(req.body);
    res.json({});
  });
  app.get('/boom', () => {
    throw new Error('fallo-secreto /ruta/interna');
  });
  app.use(notFoundHandler);
  app.use(errorHandler);
  const srv: Server = await new Promise((resolve) => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = `http://127.0.0.1:${(srv.address() as AddressInfo).port}`;
  try {
    const z1 = await fetch(base + '/z', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(z1.status, 400);
    const zb = await z1.json();
    assert.equal(zb.error.code, 'VALIDATION_ERROR');
    assert.equal(zb.error.details[0].path, 'a');

    const b1 = await fetch(base + '/boom');
    assert.equal(b1.status, 500);
    const text = await b1.text();
    assert.equal(JSON.parse(text).error.code, 'INTERNAL');
    assert.ok(!text.includes('fallo-secreto'), 'no debe filtrar el mensaje interno');
    assert.ok(!/\n\s+at /.test(text) && !text.includes('.ts:'), 'no debe incluir stack');
  } finally {
    srv.closeAllConnections();
    await new Promise<void>((r) => srv.close(() => r()));
  }
});

// ───────── T22 · sin `enum` en el código ─────────
async function walk(dir: string): Promise<string[]> {
  const out: string[] = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...(await walk(p)));
    else if (p.endsWith('.ts')) out.push(p);
  }
  return out;
}

test('T22: ningún `enum` de TypeScript en src (solo z.enum)', async () => {
  const offenders: string[] = [];
  for (const f of await walk(SRC)) {
    const lines = (await readFile(f, 'utf8')).split('\n');
    lines.forEach((l, i) => {
      if (/(^|[^.\w])enum\s+\w/.test(l)) offenders.push(`${f}:${i + 1}: ${l.trim()}`);
    });
  }
  assert.deepEqual(offenders, []);
});

// ───────── S01 · cabeceras y límite de body (vía app real) ─────────
test('S01: cabeceras de seguridad y sin X-Powered-By; 200 kB → 413 JSON', async () => {
  const res = await fetch(t.baseUrl + '/api/health');
  assert.equal(res.headers.get('x-powered-by'), null);
  assert.equal(res.headers.get('content-security-policy'), "default-src 'none'; frame-ancestors 'none'");
  const big = await t.request('POST', '/api/health', { x: 'a'.repeat(200_000) });
  assert.equal(big.status, 413);
  assert.equal(big.body.error.code, 'PAYLOAD_TOO_LARGE');
});
