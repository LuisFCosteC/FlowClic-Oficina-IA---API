import { z } from 'zod';

export const agentStatus = z.enum(['IDLE', 'WORKING', 'REVIEW', 'BLOCKED', 'SLEEP_QUOTA']);
export const ticketStatus = z.enum(['BACKLOG', 'IN_PROGRESS', 'REVIEW', 'AWAITING_APPROVAL', 'DONE']);
export const priority = z.enum(['HIGH', 'MEDIUM', 'LOW']);
export const modelTier = z.enum(['opus_pro', 'sonnet_pro', 'haiku_flash']);
export const approvalStatus = z.enum(['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED']);
export const approvalCategory = z.enum(['Arquitectura', 'Despliegue', 'Seguridad', 'Datos']);
export const memoryKind = z.enum(['NOTE', 'DECISION']);

const text = z.string().trim().min(1);
const nullableText = z.string().nullable();

export const avatarSchema = z.object({
  color: z.string().min(1),
  glasses: z.boolean().optional(),
  hairStyle: z.enum(['short', 'long', 'curly', 'bun', 'parted']).optional(),
});

// ── Agentes ──
export const agentCreateSchema = z.object({
  name: text,
  role: text,
  character: text.optional(),
  status: agentStatus.optional(),
  avatar: avatarSchema.optional(),
  systemPrompt: z.string().optional(),
  modelTier: modelTier.optional(),
  isCto: z.boolean().optional(),
  project: nullableText.optional(),
  currentTask: nullableText.optional(),
});

// Parcial y estricto; `status` va por su endpoint propio.
export const agentUpdateSchema = z.strictObject({
  name: text.optional(),
  role: text.optional(),
  character: text.optional(),
  avatar: avatarSchema.optional(),
  systemPrompt: z.string().optional(),
  modelTier: modelTier.optional(),
  isCto: z.boolean().optional(),
  project: nullableText.optional(),
  currentTask: nullableText.optional(),
});

export const agentStatusBodySchema = z.object({
  status: agentStatus,
  currentTask: z.string().optional(),
});

// ── Tickets ──
export const ticketCreateSchema = z.object({
  title: text,
  description: z.string().optional(),
  status: ticketStatus.optional(),
  priority: priority.optional(),
  assignedAgentId: nullableText.optional(),
  project: nullableText.optional(),
  modelTier: modelTier.optional(),
  estimatedCostUsd: z.number().min(0).optional(),
});

export const ticketUpdateSchema = z.strictObject({
  title: text.optional(),
  description: z.string().optional(),
  priority: priority.optional(),
  project: nullableText.optional(),
  modelTier: modelTier.optional(),
  estimatedCostUsd: z.number().min(0).optional(),
  position: z.number().int().min(0).optional(),
});

export const ticketStatusBodySchema = z.object({ status: ticketStatus });
export const ticketAssignBodySchema = z.object({ agentId: z.string().min(1).nullable() });
export const ticketContinueBodySchema = z.object({ note: z.string().optional() });

export const ticketListQuerySchema = z.object({
  status: ticketStatus.optional(),
  agentId: z.string().min(1).optional(),
  project: z.string().min(1).optional(),
});

// ── Aprobaciones ──
export const approvalCreateSchema = z.object({
  title: text,
  ticketId: z.string().min(1).nullable().optional(),
  agentId: z.string().min(1).nullable().optional(),
  category: approvalCategory.optional(),
  summary: z.string().optional(),
  reviewerNote: z.string().optional(),
  estimatedTokens: z.number().int().min(0).optional(),
});

export const approvalUpdateSchema = z.strictObject({
  title: text.optional(),
  summary: z.string().optional(),
  reviewerNote: z.string().optional(),
  category: approvalCategory.optional(),
});

export const approvalDecisionSchema = z.object({
  decision: z.enum(['APPROVED', 'REJECTED']),
  note: z.string().optional(),
});

export const approvalListQuerySchema = z.object({ status: approvalStatus.optional() });

// ── Memoria ──
export const memoryCreateSchema = z.object({
  kind: memoryKind,
  title: text,
  content: z.string().optional(),
  project: nullableText.optional(),
  ticketId: z.string().min(1).nullable().optional(),
  author: z.string().min(1).optional(),
});

export const memoryUpdateSchema = z.strictObject({
  kind: memoryKind.optional(),
  title: text.optional(),
  content: z.string().optional(),
  project: nullableText.optional(),
  ticketId: z.string().min(1).nullable().optional(),
});

export const memoryListQuerySchema = z.object({
  kind: memoryKind.optional(),
  project: z.string().min(1).optional(),
});
