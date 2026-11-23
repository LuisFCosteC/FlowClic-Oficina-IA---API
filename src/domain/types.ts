// DTOs de la API (PLAN §6). Uniones de string; sin `enum` (type stripping de Node).

export type AgentStatus = 'IDLE' | 'WORKING' | 'REVIEW' | 'BLOCKED' | 'SLEEP_QUOTA';
export type TicketStatus = 'BACKLOG' | 'IN_PROGRESS' | 'REVIEW' | 'AWAITING_APPROVAL' | 'DONE';
export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';
export type ModelTier = 'opus_pro' | 'sonnet_pro' | 'haiku_flash';
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
export type ApprovalCategory = 'Arquitectura' | 'Despliegue' | 'Seguridad' | 'Datos';
export type MemoryKind = 'NOTE' | 'DECISION';
export type TicketEventType =
  | 'CREATED'
  | 'UPDATED'
  | 'STATUS_CHANGED'
  | 'ASSIGNED'
  | 'CONTINUED'
  | 'APPROVAL_REQUESTED'
  | 'APPROVAL_DECIDED'
  | 'APPROVAL_CANCELLED'
  | 'DELETED';

export interface AgentAvatar {
  color: string;
  glasses?: boolean;
  hairStyle?: 'short' | 'long' | 'curly' | 'bun' | 'parted';
}

export interface Agent {
  id: string;
  name: string;
  character: string;
  role: string;
  status: AgentStatus;
  avatar: AgentAvatar;
  systemPrompt: string;
  modelTier: ModelTier;
  isCto: boolean;
  currentTask: string | null;
  project: string | null;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}
export type AgentCreate = Pick<Agent, 'name' | 'role'> &
  Partial<Pick<Agent, 'character' | 'status' | 'avatar' | 'systemPrompt' | 'modelTier' | 'isCto' | 'project' | 'currentTask'>>;

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: Priority;
  assignedAgentId: string | null;
  project: string | null;
  modelTier: ModelTier;
  estimatedCostUsd: number;
  position: number;
  createdAt: string;
  updatedAt: string;
}
export type TicketCreate = Pick<Ticket, 'title'> &
  Partial<Omit<Ticket, 'id' | 'createdAt' | 'updatedAt' | 'position'>>;

export interface TicketEvent {
  id: string;
  ticketId: string;
  type: TicketEventType;
  fromValue: string | null;
  toValue: string | null;
  actor: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface Approval {
  id: string;
  ticketId: string | null;
  agentId: string | null;
  title: string;
  category: ApprovalCategory;
  summary: string;
  reviewerNote: string;
  estimatedTokens: number;
  status: ApprovalStatus;
  decisionNote: string | null;
  decidedBy: string | null;
  requestedAt: string;
  decidedAt: string | null;
}

export interface MemoryEntry {
  id: string;
  kind: MemoryKind;
  title: string;
  content: string;
  project: string | null;
  ticketId: string | null;
  author: string;
  createdAt: string;
  updatedAt: string;
}
