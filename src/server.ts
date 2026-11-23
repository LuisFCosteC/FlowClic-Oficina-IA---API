import { env } from './config/env.ts';
import { getDb } from './db/client.ts';
import { createApp } from './app.ts';

const db = await getDb();
const app = createApp({ db, corsOrigin: env.CORS_ORIGIN });

const server = app.listen(env.PORT, () => {
  console.log(`API escuchando en http://localhost:${env.PORT}`);
});

function shutdown() {
  server.close(() => {
    db.close();
    process.exit(0);
  });
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
