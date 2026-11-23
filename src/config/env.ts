import { z } from 'zod';

const schema = z.object({
  HOST: z.string().min(1).default('127.0.0.1'),
  PORT: z.coerce.number().int().min(1).max(65535).default(4000),
  TURSO_DATABASE_URL: z
    .string({ error: 'falta TURSO_DATABASE_URL (p. ej. file:local.db)' })
    .min(1, 'TURSO_DATABASE_URL no puede estar vacía'),
  TURSO_AUTH_TOKEN: z
    .string()
    .optional()
    .transform((v) => (v && v.trim() !== '' ? v : undefined)),
  CORS_ORIGIN: z.string().min(1).default('http://localhost:3000'),
  ORCHESTRATOR: z.literal('noop').default('noop'),
});

export type Env = z.infer<typeof schema>;

export function parseEnv(source: Record<string, string | undefined>): Env {
  const result = schema.safeParse(source);
  if (!result.success) {
    const detail = result.error.issues
      .map((i) => `  - ${i.path.join('.') || '(env)'}: ${i.message}`)
      .join('\n');
    throw new Error(`Configuración de entorno inválida:\n${detail}`);
  }
  return result.data;
}

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
