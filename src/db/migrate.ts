import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Client } from '@libsql/client';

const DEFAULT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../migrations');

export interface MigrationResult {
  applied: string[];
  skipped: number;
}

/** Aplica en orden las migraciones NNN_nombre.sql pendientes; cada una en su transacción. */
export async function migrate(client: Client, dir: string = DEFAULT_DIR): Promise<MigrationResult> {
  await client.execute(`CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
  )`);

  const files = (await readdir(dir)).filter((f) => /^\d+_.+\.sql$/.test(f)).sort();
  const done = await client.execute('SELECT version FROM schema_migrations');
  const doneVersions = new Set(done.rows.map((r) => Number(r.version)));

  const applied: string[] = [];
  for (const file of files) {
    const version = Number.parseInt(file.split('_')[0] ?? '', 10);
    if (doneVersions.has(version)) continue;

    const sql = await readFile(path.join(dir, file), 'utf8');
    const tx = await client.transaction('write');
    try {
      await tx.executeMultiple(sql);
      await tx.execute({
        sql: 'INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)',
        args: [version, file, new Date().toISOString()],
      });
      await tx.commit();
    } catch (err) {
      await tx.rollback();
      throw new Error(`Migración ${file} falló: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      tx.close();
    }
    applied.push(file);
  }
  return { applied, skipped: files.length - applied.length };
}

if (import.meta.main) {
  const { getDb } = await import('./client.ts');
  const db = await getDb();
  try {
    const { applied, skipped } = await migrate(db);
    if (applied.length === 0) console.log(`Sin migraciones pendientes (${skipped} ya aplicadas).`);
    else for (const f of applied) console.log(`Aplicada: ${f}`);
  } catch (err) {
    console.error(err instanceof Error ? err.message : err);
    process.exitCode = 1;
  } finally {
    db.close();
  }
}
