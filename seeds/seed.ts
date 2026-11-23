import type { Client, InStatement } from '@libsql/client';

const AGENTS = [
  { id: 'sheldon', name: 'Sheldon', character: 'Sheldon Cooper', role: 'CTO', avatar: { color: '#F59E0B', hairStyle: 'parted' }, isCto: 1 },
  { id: 'leonard', name: 'Leonard', character: 'Leonard Hofstadter', role: 'Senior Full-Stack', avatar: { color: '#38BDF8', glasses: true, hairStyle: 'short' }, isCto: 0 },
  { id: 'penny', name: 'Penny', character: 'Penny', role: 'Frontend web/móvil', avatar: { color: '#EC4899', hairStyle: 'long' }, isCto: 0 },
  { id: 'raj', name: 'Raj', character: 'Rajesh Koothrappali', role: 'QA', avatar: { color: '#6366F1', hairStyle: 'short' }, isCto: 0 },
];

// Tickets sin agente asignado: así los agentes semilla (IDLE) siguen coherentes con la regla R1.
const TICKETS = [
  { id: 'seed-ticket-1', title: 'Definir alcance de la landing', description: 'Reunir requisitos y secciones de la landing.', status: 'BACKLOG', priority: 'MEDIUM', project: 'FlowClic Web' },
  { id: 'seed-ticket-2', title: 'Diseñar modelo de datos de clientes', description: 'Tablas y relaciones iniciales.', status: 'IN_PROGRESS', priority: 'HIGH', project: 'FlowClic CRM' },
  { id: 'seed-ticket-3', title: 'Revisar flujo de autenticación', description: 'Pendiente de revisión técnica.', status: 'REVIEW', priority: 'MEDIUM', project: 'FlowClic CRM' },
  { id: 'seed-ticket-4', title: 'Plan de despliegue a producción', description: 'Requiere aprobación del CEO.', status: 'AWAITING_APPROVAL', priority: 'HIGH', project: 'FlowClic Web' },
];

/** Inserta los datos semilla. Idempotente (INSERT OR IGNORE). */
export async function seed(client: Client): Promise<void> {
  const now = new Date().toISOString();
  const stmts: InStatement[] = [];

  for (const a of AGENTS) {
    stmts.push({
      sql: `INSERT OR IGNORE INTO agents (id, name, character, role, status, avatar, is_cto, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'IDLE', ?, ?, ?, ?)`,
      args: [a.id, a.name, a.character, a.role, JSON.stringify(a.avatar), a.isCto, now, now],
    });
  }

  TICKETS.forEach((t, i) => {
    stmts.push({
      sql: `INSERT OR IGNORE INTO tickets (id, title, description, status, priority, project, position, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [t.id, t.title, t.description, t.status, t.priority, t.project, i, now, now],
    });
    stmts.push({
      sql: `INSERT OR IGNORE INTO ticket_events (id, ticket_id, type, from_value, to_value, actor, payload, created_at)
            VALUES (?, ?, 'CREATED', NULL, ?, 'human', '{}', ?)`,
      args: [`seed-event-${i + 1}`, t.id, t.status, now],
    });
  });

  stmts.push({
    sql: `INSERT OR IGNORE INTO approvals (id, ticket_id, title, category, summary, reviewer_note, status, requested_at)
          VALUES ('seed-approval-1', 'seed-ticket-4', 'Plan de despliegue a producción', 'Despliegue',
                  'Despliegue inicial de la landing.', 'Revisar variables de entorno antes de aprobar.', 'PENDING', ?)`,
    args: [now],
  });
  stmts.push({
    sql: `INSERT OR IGNORE INTO project_memory (id, kind, title, content, project, author, created_at, updated_at)
          VALUES ('seed-memory-1', 'NOTE', 'Convenciones del proyecto', 'Usar TypeScript estricto y commits pequeños.', 'FlowClic Web', 'human', ?, ?)`,
    args: [now, now],
  });

  await client.batch(stmts, 'write');
}

if (import.meta.main) {
  const { getDb } = await import('../src/db/client.ts');
  const db = await getDb();
  try {
    await seed(db);
    const n = await db.execute('SELECT COUNT(*) AS n FROM agents');
    console.log(`Semilla aplicada. Agentes en la BD: ${n.rows[0]?.n}`);
  } catch (err) {
    console.error(err instanceof Error ? err.message : err);
    process.exitCode = 1;
  } finally {
    db.close();
  }
}
