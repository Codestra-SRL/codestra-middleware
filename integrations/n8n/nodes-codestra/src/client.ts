import { createHmac, randomUUID } from 'node:crypto';

export type CodestraCredential = { baseUrl: string; serviceToken: string; hmacSecret: string };
export type CodestraRequest = { method: 'GET' | 'POST' | 'PATCH' | 'DELETE'; path: string; body?: unknown; idempotencyKey?: string; correlationId?: string };

export function signedHeaders(credential: CodestraCredential, body: string, now = Math.floor(Date.now() / 1000)): Record<string, string> {
  const nonce = randomUUID();
  const signature = createHmac('sha256', credential.hmacSecret).update(`${now}.${nonce}.${body}`).digest('hex');
  return {
    Authorization: `Bearer ${credential.serviceToken}`,
    'Content-Type': 'application/json',
    'X-Codestra-Timestamp': String(now),
    'X-Codestra-Nonce': nonce,
    'X-Codestra-Signature': signature,
  };
}

export async function codestraRequest(credential: CodestraCredential, request: CodestraRequest, timeoutMs = 15_000): Promise<unknown> {
  if (!credential.baseUrl.startsWith('https://')) throw new Error('CODESTRA_TLS_REQUIRED');
  const body = request.body === undefined ? '' : JSON.stringify(request.body);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), Math.min(Math.max(timeoutMs, 1000), 30_000));
  try {
    const response = await fetch(new URL(request.path, credential.baseUrl), {
      method: request.method,
      headers: {
        ...signedHeaders(credential, body),
        'X-Correlation-ID': request.correlationId ?? randomUUID(),
        ...(request.idempotencyKey ? { 'Idempotency-Key': request.idempotencyKey } : {}),
      },
      body: body || undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      const retryable = response.status === 429 || response.status >= 500;
      throw new Error(retryable ? 'CODESTRA_TEMPORARILY_UNAVAILABLE' : 'CODESTRA_REQUEST_REJECTED');
    }
    return response.status === 204 ? {} : response.json();
  } finally {
    clearTimeout(timer);
  }
}
