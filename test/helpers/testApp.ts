import { mkdtemp, rm } from 'node:fs/promises';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import type { Client } from '@libsql/client';
import { createApp } from '../../src/app.ts';
import { createDb } from '../../src/db/client.ts';
import { migrate } from '../../src/db/migrate.ts';
import { createBus } from '../../src/events/bus.ts';
import type { EventBus } from '../../src/events/bus.ts';
import { seed } from '../../seeds/seed.ts';

export interface TestApp {
  baseUrl: string;
  db: Client;
  bus: EventBus;
  /** fetch contra la app; devuelve status y body JSON (o null si no hay body). */
  request(method: string, url: string, body?: unknown): Promise<{ status: number; body: any }>;
  close(): Promise<void>;
}

/** BD temporal en os.tmpdir() (nunca local.db), migrada y (opcional) sembrada, con la app en puerto efímero. */
export async function startTestApp(options: { seed?: boolean } = {}): Promise<TestApp> {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'flowclic-test-'));
  const dbFile = path.join(dir, 'test.db').split(path.sep).join('/');
  const db = createDb({ url: `file:${dbFile}` });
  await migrate(db);
  if (options.seed ?? true) await seed(db);

  const bus = createBus();
  const app = createApp({ db, corsOrigin: 'http://localhost:3000', bus });
  const server: Server = await new Promise((resolve) => {
    const s = app.listen(0, '127.0.0.1', () => resolve(s));
  });
  const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

  return {
    baseUrl,
    db,
    bus,
    async request(method, url, body) {
      const res = await fetch(baseUrl + url, {
        method,
        headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await res.text();
      return { status: res.status, body: text ? JSON.parse(text) : null };
    },
    async close() {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      db.close();
      await rm(dir, { recursive: true, force: true });
    },
  };
}
