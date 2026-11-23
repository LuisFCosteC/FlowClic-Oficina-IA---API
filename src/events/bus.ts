import { EventEmitter } from 'node:events';
import type { Agent, Approval, MemoryEntry, Ticket, TicketEvent } from '../domain/types.ts';

/** Mapa tipo de evento → payload (tabla SSE de PLAN §6). */
export interface DomainEventMap {
  'agent.created': Agent;
  'agent.updated': Agent;
  'agent.archived': { id: string };
  'ticket.created': Ticket;
  'ticket.updated': Ticket;
  'ticket.deleted': { id: string };
  'ticket.event': TicketEvent;
  'approval.created': Approval;
  'approval.updated': Approval;
  'memory.created': MemoryEntry;
  'memory.updated': MemoryEntry;
  'memory.deleted': { id: string };
}

export type DomainEventType = keyof DomainEventMap;

export type DomainEvent = {
  [K in DomainEventType]: { type: K; payload: DomainEventMap[K] };
}[DomainEventType];

type Handler<K extends DomainEventType> = (payload: DomainEventMap[K]) => void;
type AnyHandler = (event: DomainEvent) => void;

const ANY = '*';

export class EventBus {
  private readonly emitter = new EventEmitter();

  constructor() {
    this.emitter.setMaxListeners(0);
  }

  emit<K extends DomainEventType>(type: K, payload: DomainEventMap[K]): void {
    const event = { type, payload } as DomainEvent;
    this.emitter.emit(type, payload);
    this.emitter.emit(ANY, event);
  }

  /** Suscribe a un tipo concreto. Devuelve la función para darse de baja. */
  on<K extends DomainEventType>(type: K, handler: Handler<K>): () => void {
    this.emitter.on(type, handler);
    return () => this.emitter.off(type, handler);
  }

  /** Suscribe a todos los eventos. Devuelve la función para darse de baja. */
  onAny(handler: AnyHandler): () => void {
    this.emitter.on(ANY, handler);
    return () => this.emitter.off(ANY, handler);
  }

  listenerCount(): number {
    return this.emitter.listenerCount(ANY);
  }
}

export function createBus(): EventBus {
  return new EventBus();
}
