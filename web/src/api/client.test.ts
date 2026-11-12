import { describe, expect, it } from 'vitest';
import { mockApi } from '../test/utils';
import { api, ApiError, buildUrl } from './client';

describe('buildUrl', () => {
  it('fills path parameters and drops empty query values', () => {
    expect(buildUrl('/applications/{application_id}', { application_id: 'a b' }, { status: 'open', x: undefined })).toBe(
      '/applications/a%20b?status=open',
    );
  });
});

describe('api', () => {
  it('sends JSON and returns the parsed body', async () => {
    const { calls } = mockApi({ 'POST /applications/': { status: 201, body: { id: '1', company: 'Acme' } } });
    const created = await api.post('/applications/', { body: { company: 'Acme', role: 'Dev', status: 'Applied' } });
    expect(created).toMatchObject({ company: 'Acme' });
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/applications/', body: { company: 'Acme', role: 'Dev', status: 'Applied' } });
  });

  it('sends the X-Requested-With header the backend needs for changes', async () => {
    let headers: Headers | undefined;
    globalThis.fetch = ((_url: string, init?: RequestInit) => {
      headers = new Headers(init?.headers);
      return Promise.resolve(new Response('{}', { status: 200 }));
    }) as typeof fetch;
    await api.delete('/mail');
    expect(headers?.get('X-Requested-With')).toBe('XMLHttpRequest');
  });

  it('turns a string detail into the error message', async () => {
    mockApi({ 'POST /applications/sync': { status: 409, body: { detail: 'A sync is already running' } } });
    const error = await api.post('/applications/sync').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe('A sync is already running');
  });

  it('uses the first validation message for 422', async () => {
    mockApi({
      'POST /applications/': {
        status: 422,
        body: { detail: [{ loc: ['body', 'company'], msg: 'Value error, This field is required' }] },
      },
    });
    const error = (await api.post('/applications/', { body: { company: ' ', role: 'x', status: 'Applied' } }).catch((e: unknown) => e)) as ApiError;
    expect(error.message).toBe('This field is required');
  });

  it('uses the message of a structured detail', async () => {
    mockApi({ 'GET /mail/status': { status: 502, body: { detail: { code: 'auth', message: 'Gmail refused the login' } } } });
    const error = (await api.get('/mail/status').catch((e: unknown) => e)) as ApiError;
    expect(error.message).toBe('Gmail refused the login');
  });

  it('reports a network failure as status 0', async () => {
    mockApi({});
    globalThis.fetch = (() => Promise.reject(new TypeError('Failed to fetch'))) as typeof fetch;
    const error = (await api.get('/sync/status').catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(0);
    expect(error.message).toMatch(/not reachable/);
  });
});
