import type { paths } from './schema';

type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete';

type PathsWith<M extends HttpMethod> = {
  [P in keyof paths]: [NonNullable<paths[P][M]>] extends [never] ? never : P;
}[keyof paths];

type Operation<P extends keyof paths, M extends HttpMethod> = NonNullable<paths[P][M]>;

type JsonContent<R> = R extends { content: { 'application/json': infer J } } ? J : undefined;

export type SuccessBody<O> = O extends { responses: infer R }
  ? 200 extends keyof R
    ? JsonContent<R[200]>
    : 201 extends keyof R
      ? JsonContent<R[201]>
      : undefined
  : never;

type RequestBody<O> = O extends { requestBody?: { content: { 'application/json': infer B } } } ? B : never;
type PathParams<O> = O extends { parameters: { path?: infer P } } ? P : never;
type QueryParams<O> = O extends { parameters: { query?: infer Q } } ? Q : never;

export interface RequestOptions<O> {
  path?: PathParams<O>;
  query?: QueryParams<O>;
  body?: RequestBody<O>;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(errorMessage(status, detail));
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function errorMessage(status: number, detail: unknown): string {
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first: unknown = detail[0];
    if (first && typeof first === 'object' && 'msg' in first && typeof first.msg === 'string') {
      return first.msg.replace(/^Value error, /, '');
    }
  }
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message;
  }
  if (status === 0) return 'Jōb is not reachable. Check that it is running.';
  return `Request failed (${status})`;
}

export function buildUrl(template: string, path?: object, query?: object): string {
  let url = template;
  for (const [key, value] of Object.entries(path ?? {})) {
    url = url.replace(`{${key}}`, encodeURIComponent(String(value)));
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${url}?${qs}` : url;
}

async function request<P extends keyof paths, M extends HttpMethod>(
  method: M,
  template: P,
  options: RequestOptions<Operation<P, M>> = {},
): Promise<SuccessBody<Operation<P, M>>> {
  const url = buildUrl(template as string, options.path as object | undefined, options.query as object | undefined);
  // The backend refuses changes without X-Requested-With: other sites can't send it (CSRF).
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, { method: method.toUpperCase(), headers, body, signal: options.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, null);
  }

  const text = await response.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : data;
    throw new ApiError(response.status, detail);
  }
  return data as SuccessBody<Operation<P, M>>;
}

export const api = {
  get: <P extends PathsWith<'get'>>(path: P, options?: RequestOptions<Operation<P, 'get'>>) =>
    request('get', path, options),
  post: <P extends PathsWith<'post'>>(path: P, options?: RequestOptions<Operation<P, 'post'>>) =>
    request('post', path, options),
  put: <P extends PathsWith<'put'>>(path: P, options?: RequestOptions<Operation<P, 'put'>>) =>
    request('put', path, options),
  patch: <P extends PathsWith<'patch'>>(path: P, options?: RequestOptions<Operation<P, 'patch'>>) =>
    request('patch', path, options),
  delete: <P extends PathsWith<'delete'>>(path: P, options?: RequestOptions<Operation<P, 'delete'>>) =>
    request('delete', path, options),
};
