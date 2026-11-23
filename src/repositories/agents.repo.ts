import type { Agent, AgentAvatar, AgentStatus, ModelTier } from '../domain/types.ts';
import { buildUpdate, str, strOrNull } from './util.ts';
import type { Executor, Row } from './util.ts';

export function rowToAgent(r: Row): Agent {
  return {
    id: str(r.id),
    name: str(r.name),
    character: str(r.character),
    role: str(r.role),
    status: str(r.status) as AgentStatus,
    avatar: JSON.parse(str(r.avatar)) as AgentAvatar,
    systemPrompt: str(r.system_prompt),
    modelTier: str(r.model_tier) as ModelTier,
    isCto: Number(r.is_cto) === 1,
    currentTask: strOrNull(r.current_task),
    project: strOrNull(r.project),
    createdAt: str(r.created_at),
    updatedAt: str(r.updated_at),
    archivedAt: strOrNull(r.archived_at),
  };
}

export async function listAgents(db: Executor, opts: { includeArchived?: boolean } = {}): Promise<Agent[]> {
  const where = opts.includeArchived ? '' : 'WHERE archived_at IS NULL';
  const res = await db.execute(`SELECT * FROM agents ${where} ORDER BY created_at, name`);
  return res.rows.map(rowToAgent);
}

export async function getAgent(db: Executor, id: string): Promise<Agent | null> {
  const res = await db.execute({ sql: 'SELECT * FROM agents WHERE id = ?', args: [id] });
  const row = res.rows[0];
  return row ? rowToAgent(row) : null;
}

export async function findActiveAgentByName(db: Executor, name: string): Promise<Agent | null> {
  const res = await db.execute({ sql: 'SELECT * FROM agents WHERE name = ? AND archived_at IS NULL', args: [name] });
  const row = res.rows[0];
  return row ? rowToAgent(row) : null;
}

export async function insertAgent(db: Executor, a: Agent): Promise<void> {
  await db.execute({
    sql: `INSERT INTO agents (id, name, character, role, status, avatar, system_prompt, model_tier, is_cto,
                              current_task, project, created_at, updated_at, archived_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    args: [
      a.id, a.name, a.character, a.role, a.status, JSON.stringify(a.avatar), a.systemPrompt, a.modelTier,
      a.isCto ? 1 : 0, a.currentTask, a.project, a.createdAt, a.updatedAt, a.archivedAt,
    ],
  });
}

export interface AgentPatch {
  name?: string;
  role?: string;
  character?: string;
  avatar?: AgentAvatar;
  systemPrompt?: string;
  modelTier?: ModelTier;
  isCto?: boolean;
  project?: string | null;
  currentTask?: string | null;
}

export async function updateAgent(db: Executor, id: string, patch: AgentPatch, now: string): Promise<void> {
  const stmt = buildUpdate('agents', id, {
    name: patch.name,
    role: patch.role,
    character: patch.character,
    avatar: patch.avatar === undefined ? undefined : JSON.stringify(patch.avatar),
    system_prompt: patch.systemPrompt,
    model_tier: patch.modelTier,
    is_cto: patch.isCto === undefined ? undefined : patch.isCto ? 1 : 0,
    project: patch.project,
    current_task: patch.currentTask,
    updated_at: now,
  });
  if (stmt) await db.execute(stmt);
}

export async function setAgentStatus(
  db: Executor,
  id: string,
  status: AgentStatus,
  currentTask: string | null,
  now: string,
): Promise<void> {
  await db.execute({
    sql: 'UPDATE agents SET status = ?, current_task = ?, updated_at = ? WHERE id = ?',
    args: [status, currentTask, now, id],
  });
}

export async function archiveAgent(db: Executor, id: string, now: string): Promise<void> {
  await db.execute({ sql: 'UPDATE agents SET archived_at = ?, updated_at = ? WHERE id = ?', args: [now, now, id] });
}
