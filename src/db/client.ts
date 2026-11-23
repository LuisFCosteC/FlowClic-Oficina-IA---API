import { createClient } from '@libsql/client';
import type { Client } from '@libsql/client';

export interface DbConfig {
  url: string;
  authToken?: string | undefined;
}

/** Crea un cliente libSQL. Si el token viene vacío, no se envía. */
export function createDb(config: DbConfig): Client {
  const token = config.authToken && config.authToken.trim() !== '' ? config.authToken : undefined;
  return token ? createClient({ url: config.url, authToken: token }) : createClient({ url: config.url });
}

let shared: Client | undefined;

/** Cliente único de la aplicación (se crea en el primer uso, con el env validado). */
export async function getDb(): Promise<Client> {
  if (!shared) {
    const { env } = await import('../config/env.ts');
    shared = createDb({ url: env.TURSO_DATABASE_URL, authToken: env.TURSO_AUTH_TOKEN });
  }
  return shared;
}
