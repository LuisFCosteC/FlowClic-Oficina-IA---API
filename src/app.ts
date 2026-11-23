import cors from 'cors';
import express from 'express';
import type { Express } from 'express';
import type { Client } from '@libsql/client';
import { errorHandler, notFoundHandler } from './middleware/errors.ts';
import { requestId, securityHeaders } from './middleware/security.ts';
import type { EventBus } from './events/bus.ts';

export interface AppDeps {
  db: Client;
  corsOrigin: string;
  bus: EventBus;
}

/** Crea la app Express sin escuchar (exportable para tests). */
export function createApp(deps: AppDeps): Express {
  const app = express();
  app.disable('x-powered-by');

  app.use(requestId);
  app.use(securityHeaders);
  app.use(cors({ origin: deps.corsOrigin }));
  app.use(express.json({ limit: '100kb' }));

  // Sin sesión solo responde {ok}. (El detalle con sesión se añade con S09.)
  app.get('/api/health', async (_req, res, next) => {
    try {
      await deps.db.execute('SELECT 1');
      res.json({ ok: true });
    } catch (err) {
      next(err);
    }
  });

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
