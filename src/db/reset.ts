import { rm } from 'node:fs/promises';
import path from 'node:path';

const url = process.env.TURSO_DATABASE_URL ?? '';

if (!url.startsWith('file:')) {
  console.error(
    `db:reset solo funciona con bases locales (file:...). TURSO_DATABASE_URL actual: "${url || '(vacía)'}". No se borró nada.`,
  );
  process.exit(1);
}

const target = url.slice('file:'.length);
if (target !== '' && !target.startsWith(':memory:')) {
  const file = path.resolve(process.cwd(), target);
  for (const suffix of ['', '-wal', '-shm', '-journal']) {
    await rm(file + suffix, { force: true });
  }
  console.log(`Base local borrada: ${path.relative(process.cwd(), file)}`);
}

const { getDb } = await import('./client.ts');
const { migrate } = await import('./migrate.ts');
const { seed } = await import('../../seeds/seed.ts');

const db = await getDb();
try {
  const { applied } = await migrate(db);
  console.log(`Migraciones aplicadas: ${applied.length}`);
  await seed(db);
  console.log('Semilla aplicada.');
} catch (err) {
  console.error(err instanceof Error ? err.message : err);
  process.exitCode = 1;
} finally {
  db.close();
}
