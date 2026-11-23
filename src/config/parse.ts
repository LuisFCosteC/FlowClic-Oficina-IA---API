import { z } from 'zod';

const positiveInt = (def: number) => z.coerce.number().int().min(1).default(def);
const boolFlag = (def: 'true' | 'false') => z.enum(['true', 'false']).default(def).transform((v) => v === 'true');

const schema = z
  .object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    HOST: z.string().min(1).default('127.0.0.1'),
    PORT: z.coerce.number().int().min(1).max(65535).default(4000),
    TURSO_DATABASE_URL: z
      .string({ error: 'falta TURSO_DATABASE_URL (p. ej. file:local.db)' })
      .min(1, 'TURSO_DATABASE_URL no puede estar vacía'),
    TURSO_AUTH_TOKEN: z.string().optional(),
    CORS_ORIGIN: z.string().min(1).default('http://localhost:3000'),
    ORCHESTRATOR: z.literal('noop').default('noop'),
    // Seguridad (PLAN §12.5). Las claves las genera `npm run setup`.
    APP_ENCRYPTION_KEY: z.string().optional(),
    SESSION_SECRET: z.string().optional(),
    SESSION_IDLE_MINUTES: positiveInt(30),
    SESSION_MAX_HOURS: positiveInt(8),
    BACKUP_DIR: z.string().min(1).default('backups'),
    BACKUP_INTERVAL_HOURS: positiveInt(24),
    BACKUP_KEEP: positiveInt(14),
    ADMIN_ALLOW_DB_CHANGE: boolFlag('true'),
  })
  .superRefine((v, ctx) => {
    if (v.APP_ENCRYPTION_KEY !== undefined && Buffer.from(v.APP_ENCRYPTION_KEY, 'base64').length !== 32) {
      ctx.addIssue({ code: 'custom', path: ['APP_ENCRYPTION_KEY'], message: 'debe ser 32 bytes en base64 (ejecuta npm run setup)' });
    }
    if (v.NODE_ENV === 'production') {
      for (const key of ['APP_ENCRYPTION_KEY', 'SESSION_SECRET'] as const) {
        if (!v[key]) ctx.addIssue({ code: 'custom', path: [key], message: 'obligatoria en producción' });
      }
    }
  });

export type Env = z.infer<typeof schema>;

export function parseEnv(source: Record<string, string | undefined>): Env {
  // Una variable vacía (`CLAVE=`) equivale a no definida.
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(source)) if (v !== undefined && v.trim() !== '') cleaned[k] = v;

  const result = schema.safeParse(cleaned);
  if (!result.success) {
    const detail = result.error.issues
      .map((i) => `  - ${i.path.join('.') || '(env)'}: ${i.message}`)
      .join('\n');
    throw new Error(`Configuración de entorno inválida:\n${detail}`);
  }
  return result.data;
}
