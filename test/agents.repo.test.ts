import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startTestApp } from './helpers/testApp.ts';
import type { TestApp } from './helpers/testApp.ts';
import * as repo from '../src/repositories/agents.repo.ts';
import type { Agent } from '../src/domain/types.ts';

let t: TestApp;
before(async () => { t = await startTestApp(); });
after(async () => { await t.close(); });

const now = '2026-11-22T10:00:00.000Z';
const base: Agent = {
  id: 'howard', name: 'Howard', character: 'Howard Wolowitz', role: 'Hardware', status: 'IDLE',
  avatar: { color: '#10B981', glasses: false, hairStyle: 'bun' }, systemPrompt: 'hola', modelTier: 'haiku_flash',
  isCto: false, currentTask: null, project: 'X', createdAt: now, updatedAt: now, archivedAt: null,
};

test('list devuelve los 4 agentes semilla mapeados a camelCase con avatar objeto', async () => {
  const list = await repo.listAgents(t.db);
  assert.equal(list.length, 4);
  const sheldon = list.find((a) => a.id === 'sheldon');
  assert.equal(sheldon?.isCto, true);
  assert.deepEqual(sheldon?.avatar, { color: '#F59E0B', hairStyle: 'parted' });
});

test('insert + get + update + setStatus', async () => {
  await repo.insertAgent(t.db, base);
  assert.deepEqual(await repo.getAgent(t.db, 'howard'), base);

  await repo.updateAgent(t.db, 'howard', { role: 'Ingeniero', avatar: { color: '#000' }, isCto: true }, '2026-11-22T11:00:00.000Z');
  const upd = await repo.getAgent(t.db, 'howard');
  assert.equal(upd?.role, 'Ingeniero');
  assert.equal(upd?.isCto, true);
  assert.deepEqual(upd?.avatar, { color: '#000' });
  assert.equal(upd?.updatedAt, '2026-11-22T11:00:00.000Z');

  await repo.setAgentStatus(t.db, 'howard', 'WORKING', 'Tarea X', now);
  const w = await repo.getAgent(t.db, 'howard');
  assert.equal(w?.status, 'WORKING');
  assert.equal(w?.currentTask, 'Tarea X');
});

test('get de id inexistente devuelve null', async () => {
  assert.equal(await repo.getAgent(t.db, 'nadie'), null);
});

test('archive oculta al agente del listado salvo includeArchived y libera el nombre', async () => {
  await repo.archiveAgent(t.db, 'howard', now);
  assert.equal((await repo.listAgents(t.db)).some((a) => a.id === 'howard'), false);
  const all = await repo.listAgents(t.db, { includeArchived: true });
  assert.equal(all.find((a) => a.id === 'howard')?.archivedAt, now);
  assert.equal(await repo.findActiveAgentByName(t.db, 'Howard'), null);
});
