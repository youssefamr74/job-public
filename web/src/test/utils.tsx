import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Tooltip from '@radix-ui/react-tooltip';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { vi } from 'vitest';
import type { Application } from '../api/types';

export interface Call {
  method: string;
  url: string;
  body: unknown;
}

type Handler = (call: Call) => { status?: number; body?: unknown } | undefined;

function isSpec(value: unknown): value is { status: number; body?: unknown } {
  return typeof value === 'object' && value !== null && typeof (value as { status?: unknown }).status === 'number';
}

/** Stubs fetch. Each handler key is "METHOD /path" (query string ignored). */
export function mockApi(handlers: Record<string, Handler | unknown>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const call = { method, url, body };
    calls.push(call);
    const key = `${method} ${url.split('?')[0]}`;
    const handler = handlers[key];
    if (handler === undefined) return new Response(JSON.stringify({ detail: `No mock for ${key}` }), { status: 404 });
    const result = typeof handler === 'function' ? (handler as Handler)(call) : isSpec(handler) ? handler : { body: handler };
    const status = result?.status ?? 200;
    // A 204 can't have a body, not even an empty one.
    const text = status === 204 ? null : result?.body === undefined ? '' : JSON.stringify(result.body);
    return new Response(text, { status });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}

export function renderWithProviders(ui: ReactElement, { route = '/applications' } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter([{ path: '*', element: ui }], { initialEntries: [route] });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider>
        <RouterProvider router={router} />
      </Tooltip.Provider>
    </QueryClientProvider>,
  );
  return { ...result, queryClient, router };
}

const DAY = 24 * 60 * 60 * 1000;

export function daysAgo(days: number): string {
  return new Date(Date.now() - days * DAY).toISOString();
}

let counter = 0;

export function makeApplication(overrides: Partial<Application> = {}): Application {
  counter += 1;
  return {
    id: `00000000-0000-0000-0000-${String(counter).padStart(12, '0')}`,
    company: 'Northwind Labs',
    role: 'Data Engineer',
    status: 'Applied',
    applied_date: daysAgo(5),
    source: 'gmail',
    notes: null,
    interview_date: null,
    location: null,
    raw_metadata: null,
    action_needed: false,
    manually_modified: false,
    email_count: 1,
    last_activity_at: daysAgo(5),
    no_reply_days: null,
    interview_held: false,
    no_news_days: null,
    followup_snoozed_until: null,
    needs_followup: false,
    progress_step: 1,
    timeline: [],
    ...overrides,
  };
}
