import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

/** Rellena `CLAVE=` vacías con 32 bytes aleatorios en base64. */
export function fillSecrets(template: string, keys: string[]): string {
  let out = template;
  for (const key of keys) {
    out = out.replace(new RegExp(`^${key}=\\s*$`, 'm'), () => `${key}=${randomBytes(32).toString('base64')}`);
  }
  return out;
}

export async function setup(cwd: string): Promise<'created' | 'exists'> {
  const envPath = path.join(cwd, '.env');
  if (existsSync(envPath)) return 'exists'; // nunca se sobrescribe
  const template = await readFile(path.join(cwd, '.env.example'), 'utf8');
  await writeFile(envPath, fillSecrets(template, ['APP_ENCRYPTION_KEY', 'SESSION_SECRET']), { flag: 'wx' });
  return 'created';
}

if (import.meta.main) {
  const result = await setup(process.cwd());
  console.log(
    result === 'created'
      ? '.env creado con claves aleatorias (APP_ENCRYPTION_KEY, SESSION_SECRET). Guárdalo: no está en git.'
      : '.env ya existe: no se modificó nada.',
  );
}
