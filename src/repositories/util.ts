import type { Client, InValue, ResultSet, Transaction } from '@libsql/client';

/** Cliente o transacción: los repositorios aceptan ambos. */
export type Executor = Pick<Client | Transaction, 'execute'>;

export type Row = ResultSet['rows'][number];

export const str = (v: unknown): string => String(v);
export const strOrNull = (v: unknown): string | null => (v === null || v === undefined ? null : String(v));

/** Construye un UPDATE parcial a partir de {columna: valor}. Devuelve null si no hay nada que cambiar. */
export function buildUpdate(
  table: string,
  id: string,
  columns: Record<string, InValue | undefined>,
): { sql: string; args: InValue[] } | null {
  const entries = Object.entries(columns).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return null;
  const sets = entries.map(([c]) => `${c} = ?`).join(', ');
  return { sql: `UPDATE ${table} SET ${sets} WHERE id = ?`, args: [...entries.map(([, v]) => v as InValue), id] };
}
