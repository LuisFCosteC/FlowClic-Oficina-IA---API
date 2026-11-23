import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createBus } from '../src/events/bus.ts';
import type { DomainEvent } from '../src/events/bus.ts';
import type { Agent } from '../src/domain/types.ts';

const agent: Agent = {
  id: 'a1', name: 'A', character: 'A', role: 'QA', status: 'IDLE', avatar: { color: '#fff' },
  systemPrompt: '', modelTier: 'sonnet_pro', isCto: false, currentTask: null, project: null,
  createdAt: 'x', updatedAt: 'x', archivedAt: null,
};

test('un suscriptor recibe el evento con su payload tipado', () => {
  const bus = createBus();
  const seen: Agent[] = [];
  bus.on('agent.updated', (a) => seen.push(a));
  bus.emit('agent.updated', agent);
  assert.equal(seen.length, 1);
  assert.equal(seen[0]?.id, 'a1');
});

test('onAny recibe {type, payload} y no recibe tras darse de baja', () => {
  const bus = createBus();
  const events: DomainEvent[] = [];
  const off = bus.onAny((e) => events.push(e));
  bus.emit('ticket.deleted', { id: 't1' });
  off();
  bus.emit('ticket.deleted', { id: 't2' });
  assert.deepEqual(events, [{ type: 'ticket.deleted', payload: { id: 't1' } }]);
  assert.equal(bus.listenerCount(), 0);
});

test('un tipo no recibe eventos de otro tipo', () => {
  const bus = createBus();
  let n = 0;
  bus.on('agent.created', () => n++);
  bus.emit('agent.updated', agent);
  assert.equal(n, 0);
});
