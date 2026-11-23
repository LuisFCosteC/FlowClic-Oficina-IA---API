import { parseEnv } from './parse.ts';
import type { Env } from './parse.ts';

export type { Env };
export { parseEnv };

function load(): Env {
  try {
    return parseEnv(process.env);
  } catch (err) {
    console.error(err instanceof Error ? err.message : err);
    console.error('Revisa tu archivo .env (usa .env.example como base).');
    process.exit(1);
  }
}

export const env: Env = load();
