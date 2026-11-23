import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startTestApp } from './helpers/testApp.ts';
import type { TestApp } from './helpers/testApp.ts';

let t: TestApp;
before(async () => { t = await startTestApp(); });
after(async () => { await t.close(); });

const now = '2026-11-22T10:00:00.000Z';
const insertUser = (id: string, email: string, role = 'VIEWER') =>
  t.db.execute({
    sql: `INSERT INTO users (id, email, display_name, password_hash, role, password_changed_at, created_at, updated_at)
          VALUES (?, ?, 'X', 'h', ?, ?, ?, ?)`,
    args: [id, email, role, now, now, now],
  });

test('002_security: tablas creadas y la semilla no crea usuarios', async () => {
  const n = await t.db.execute('SELECT COUNT(*) AS n FROM users');
  assert.equal(Number(n.rows[0]?.n), 0);
});

test('email repetido falla por índice único', async () => {
  await insertUser('u1', 'a@x.com');
  await assert.rejects(insertUser('u2', 'a@x.com'), /UNIQUE/);
});

test('rol inválido falla por CHECK', async () => {
  await assert.rejects(insertUser('u3', 'b@x.com', 'ROOT'), /CHECK/);
});
