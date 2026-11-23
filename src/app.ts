import cors from 'cors';
import express from 'express';
import type { Express } from 'express';
import type { Client } from '@libsql/client';
import { errorHandler, notFoundHandler } from './middleware/errors.ts';
import pkg from '../package.json' with { type: 'json' };

export interface AppDeps {
  db: Client;
  corsOrigin: string;
}

/** Crea la app Express sin escuchar (exportable para tests). */
export function createApp(deps: AppDeps): Express {
  const app = express();

  app.use(cors({ origin: deps.corsOrigin }));
  app.use(express.json());

  app.get('/api/health', async (_req, res, next) => {
    try {
      await deps.db.execute('SELECT 1');
      res.json({ ok: true, db: 'up', version: pkg.version });
    } catch (err) {
      next(err);
    }
  });

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
