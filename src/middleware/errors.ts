import type { ErrorRequestHandler, RequestHandler } from 'express';
import { ZodError } from 'zod';

export type ErrorCode = 'VALIDATION_ERROR' | 'NOT_FOUND' | 'CONFLICT' | 'UNPROCESSABLE' | 'PAYLOAD_TOO_LARGE' | 'INTERNAL';

const STATUS: Record<ErrorCode, number> = {
  VALIDATION_ERROR: 400,
  NOT_FOUND: 404,
  CONFLICT: 409,
  UNPROCESSABLE: 422,
  PAYLOAD_TOO_LARGE: 413,
  INTERNAL: 500,
};

/** Error de dominio con código HTTP asociado. */
export class AppError extends Error {
  readonly code: ErrorCode;
  readonly details: unknown[] | undefined;
  constructor(code: ErrorCode, message: string, details?: unknown[]) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.details = details;
  }
  get status(): number {
    return STATUS[this.code];
  }
}

export const notFound = (message: string) => new AppError('NOT_FOUND', message);
export const conflict = (message: string) => new AppError('CONFLICT', message);
export const unprocessable = (message: string) => new AppError('UNPROCESSABLE', message);
export const validation = (message: string, details?: unknown[]) => new AppError('VALIDATION_ERROR', message, details);

function body(code: ErrorCode, message: string, details: unknown[] = []) {
  return { error: { code, message, details } };
}

export const notFoundHandler: RequestHandler = (req, res) => {
  res.status(404).json(body('NOT_FOUND', `Ruta no encontrada: ${req.method} ${req.path}`));
};

export const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  const requestId = res.locals.requestId as string | undefined;
  if (err instanceof ZodError) {
    const details = err.issues.map((i) => ({ path: i.path.join('.'), message: i.message }));
    const first = details[0];
    const message = first ? `${first.path || 'body'}: ${first.message}` : 'Datos inválidos';
    res.status(400).json(body('VALIDATION_ERROR', message, details));
    return;
  }
  if (err instanceof AppError) {
    res.status(err.status).json(body(err.code, err.message, err.details));
    return;
  }
  // JSON mal formado (body-parser)
  if (err && typeof err === 'object' && (err as { type?: string }).type === 'entity.parse.failed') {
    res.status(400).json(body('VALIDATION_ERROR', 'JSON inválido'));
    return;
  }
  if (err && typeof err === 'object' && (err as { type?: string }).type === 'entity.too.large') {
    res.status(413).json(body('PAYLOAD_TOO_LARGE', 'El cuerpo de la petición es demasiado grande'));
    return;
  }
  console.error('[error]', requestId ?? '-', err instanceof Error ? err.message : err);
  res.status(500).json(body('INTERNAL', 'Error interno del servidor'));
};
