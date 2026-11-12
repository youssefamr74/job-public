import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  AIConfigRequest,
  Application,
  ApplicationCreate,
  ApplicationMetadataUpdate,
  ApplicationUpdate,
  AnalyticsRange,
  InterviewOutcome,
  Notification,
  ReviewStatus,
} from './types';

export const keys = {
  applications: ['applications'] as const,
  today: ['applications', 'today'] as const,
  openOpportunities: ['opportunities', 'open'] as const,
  syncStatus: ['sync', 'status'] as const,
  mailStatus: ['mail', 'status'] as const,
  message: (id: string) => ['mail', 'message', id] as const,
  aiStatus: ['ai', 'status'] as const,
  opportunities: ['opportunities'] as const,
  notifications: ['notifications'] as const,
  setupStatus: ['setup', 'status'] as const,
  syncRuns: ['sync', 'runs'] as const,
  syncSettings: ['settings', 'sync'] as const,
  unreadCount: ['notifications', 'unread-count'] as const,
};

export const SYNC_POLL_RUNNING_MS = 2000;
export const SYNC_POLL_IDLE_MS = 60_000;

export function useApplications() {
  return useQuery({
    queryKey: keys.applications,
    queryFn: ({ signal }) => api.get('/applications/', { signal }),
  });
}

export function useToday() {
  return useQuery({
    queryKey: keys.today,
    queryFn: ({ signal }) => api.get('/applications/today', { signal }),
  });
}

export function useOpenOpportunities() {
  return useQuery({
    queryKey: keys.openOpportunities,
    queryFn: ({ signal }) => api.get('/opportunities/', { query: { status: 'open' }, signal }),
  });
}

export function useSyncStatus() {
  return useQuery({
    queryKey: keys.syncStatus,
    queryFn: ({ signal }) => api.get('/sync/status', { signal }),
    refetchInterval: (query) => (query.state.data?.running_run ? SYNC_POLL_RUNNING_MS : SYNC_POLL_IDLE_MS),
  });
}

export function useMailStatus() {
  return useQuery({
    queryKey: keys.mailStatus,
    queryFn: ({ signal }) => api.get('/mail/status', { signal }),
    refetchInterval: SYNC_POLL_IDLE_MS,
  });
}

export function useStartSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/applications/sync'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.syncStatus }),
  });
}

function replaceInList(queryClient: QueryClient, updated: Application) {
  queryClient.setQueryData<Application[]>(keys.applications, (list) =>
    list?.map((app) => (app.id === updated.id ? updated : app)),
  );
  void queryClient.invalidateQueries({ queryKey: keys.today, exact: true });
}

export function useUpdateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: ApplicationUpdate }) =>
      api.patch('/applications/{application_id}', { path: { application_id: id }, body: changes }),
    onMutate: async ({ id, changes }) => {
      const status = changes.status;
      if (!status) return { previous: undefined };
      await queryClient.cancelQueries({ queryKey: keys.applications });
      const previous = queryClient.getQueryData<Application[]>(keys.applications);
      queryClient.setQueryData<Application[]>(keys.applications, (list) =>
        list?.map((app) => (app.id === id ? { ...app, status } : app)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(keys.applications, context.previous);
    },
    onSuccess: (updated) => replaceInList(queryClient, updated),
  });
}

export function useUpdateDetails() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: ApplicationMetadataUpdate }) =>
      api.patch('/applications/{application_id}/metadata', { path: { application_id: id }, body: changes }),
    onSuccess: (updated) => replaceInList(queryClient, updated),
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApplicationCreate) => api.post('/applications/', { body }),
    onSuccess: (created) => {
      queryClient.setQueryData<Application[]>(keys.applications, (list) => (list ? [created, ...list] : [created]));
      void queryClient.invalidateQueries({ queryKey: keys.today, exact: true });
    },
  });
}

export function useInterviewOutcome() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, outcome }: { id: string; outcome: InterviewOutcome }) =>
      api.post('/applications/{application_id}/interview-outcome', { path: { application_id: id }, body: { outcome } }),
    onSuccess: (updated) => replaceInList(queryClient, updated),
  });
}

/** The email itself, read from the mail source when shown. Kept only in memory, and dropped soon after. */
export function useMessage(id: string | null) {
  return useQuery({
    queryKey: keys.message(id ?? ''),
    queryFn: ({ signal }) => api.get('/mail/messages/{message_id}', { path: { message_id: id ?? '' }, signal }),
    enabled: Boolean(id),
    retry: false,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
  });
}

export function useAIStatus() {
  return useQuery({
    queryKey: keys.aiStatus,
    queryFn: ({ signal }) => api.get('/ai/status', { signal }),
  });
}

function removeFromList(queryClient: QueryClient, id: string) {
  queryClient.setQueryData<Application[]>(keys.applications, (list) => list?.filter((app) => app.id !== id));
  void queryClient.invalidateQueries({ queryKey: keys.today, exact: true });
}

export interface ReviewDecision {
  id: string;
  status: ReviewStatus;
  company?: string;
  role?: string;
}

export function useSaveReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, status, company, role }: ReviewDecision) => {
      if (company !== undefined || role !== undefined) {
        await api.patch('/applications/{application_id}/metadata', {
          path: { application_id: id },
          body: { company, role },
        });
      }
      return api.patch('/applications/{application_id}', { path: { application_id: id }, body: { status } });
    },
    onSuccess: (updated) => replaceInList(queryClient, updated),
  });
}

export function useNotJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post('/applications/{application_id}/not-job', { path: { application_id: id } }),
    onSuccess: (_data, id) => removeFromList(queryClient, id),
  });
}

export function useToOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post('/applications/{application_id}/to-opportunity', { path: { application_id: id } }),
    onSuccess: (_data, id) => {
      removeFromList(queryClient, id);
      void queryClient.invalidateQueries({ queryKey: keys.opportunities });
    },
  });
}

export function useAiReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/applications/ai-review'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.applications });
      void queryClient.invalidateQueries({ queryKey: keys.aiStatus });
    },
  });
}

export type OpportunityFilter = 'open' | 'all';

export function useOpportunities(filter: OpportunityFilter) {
  return useQuery({
    queryKey: filter === 'open' ? keys.openOpportunities : ([...keys.opportunities, 'all'] as const),
    queryFn: ({ signal }) =>
      api.get('/opportunities/', { query: filter === 'open' ? { status: 'open' } : {}, signal }),
  });
}

export function useConvertOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post('/opportunities/{opportunity_id}/convert', { path: { opportunity_id: id } }),
    onSuccess: (created) => {
      queryClient.setQueryData<Application[]>(keys.applications, (list) => (list ? [created, ...list] : list));
      void queryClient.invalidateQueries({ queryKey: keys.opportunities });
      void queryClient.invalidateQueries({ queryKey: keys.today, exact: true });
    },
  });
}

export function useDismissOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post('/opportunities/{opportunity_id}/dismiss', { path: { opportunity_id: id } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.opportunities }),
  });
}

export function useAnalytics(range: AnalyticsRange) {
  return useQuery({
    queryKey: ['analytics', 'overview', range] as const,
    queryFn: ({ signal }) => api.get('/analytics/overview', { query: { range }, signal }),
  });
}

export function useWeeklyReview() {
  return useQuery({
    queryKey: ['analytics', 'weekly-review'] as const,
    queryFn: ({ signal }) => api.get('/analytics/weekly-review', { signal }),
    staleTime: 10 * 60_000,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: keys.unreadCount,
    queryFn: ({ signal }) => api.get('/notifications/unread-count', { signal }),
    refetchInterval: SYNC_POLL_IDLE_MS,
  });
}

export function useNotifications(limit: number, enabled = true) {
  return useQuery({
    queryKey: [...keys.notifications, 'list', limit] as const,
    queryFn: ({ signal }) => api.get('/notifications/', { query: { limit }, signal }),
    enabled,
  });
}

function markInCache(queryClient: QueryClient, id: string | null) {
  const now = new Date().toISOString();
  queryClient.setQueriesData<Notification[]>({ queryKey: [...keys.notifications, 'list'] }, (list) =>
    list?.map((n) => (id === null || n.id === id) && !n.read_at ? { ...n, read_at: now } : n),
  );
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post('/notifications/{notification_id}/read', { path: { notification_id: id } }),
    onMutate: (id) => markInCache(queryClient, id),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.unreadCount }),
  });
}

export function useMarkAllRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/notifications/read-all'),
    onMutate: () => markInCache(queryClient, null),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.unreadCount }),
  });
}

function invalidateMail(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: keys.mailStatus });
  void queryClient.invalidateQueries({ queryKey: keys.setupStatus });
}

export function useSetupStatus() {
  return useQuery({
    queryKey: keys.setupStatus,
    queryFn: ({ signal }) => api.get('/setup/status', { signal }),
  });
}

export function useConnectImap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; app_password: string }) => api.post('/mail/imap', { body }),
    onSuccess: () => invalidateMail(queryClient),
  });
}

export function useRedirectUri() {
  return useQuery({
    queryKey: ['mail', 'redirect-uri'] as const,
    queryFn: ({ signal }) => api.get('/mail/oauth/redirect-uri', { signal }),
    staleTime: Infinity,
  });
}

export function useStartOAuth() {
  return useMutation({
    mutationFn: (body: { client_id: string; client_secret: string }) => api.post('/mail/oauth/client', { body }),
  });
}

export function useReconnectOAuth() {
  return useMutation({ mutationFn: () => api.post('/mail/oauth/reconnect') });
}

export function useTestMail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/mail/test'),
    onSettled: () => invalidateMail(queryClient),
  });
}

export function useDisconnectMail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete('/mail'),
    onSuccess: () => invalidateMail(queryClient),
  });
}

export function useAIProviders() {
  return useQuery({
    queryKey: ['ai', 'providers'] as const,
    queryFn: ({ signal }) => api.get('/ai/providers', { signal }),
    staleTime: Infinity,
  });
}

export function useLoadModels() {
  return useMutation({
    mutationFn: (body: { provider: string; api_key?: string; base_url?: string }) => api.post('/ai/models', { body }),
  });
}

/** body_chars and batch_threshold have defaults on the server. */
export type AIConfigInput = Omit<AIConfigRequest, 'body_chars' | 'batch_threshold'> &
  Partial<Pick<AIConfigRequest, 'body_chars' | 'batch_threshold'>>;

function invalidateAI(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: keys.aiStatus });
  void queryClient.invalidateQueries({ queryKey: keys.setupStatus });
  void queryClient.invalidateQueries({ queryKey: ['analytics', 'weekly-review'] });
}

export function useSaveAI() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AIConfigInput) => api.post('/ai/config', { body: body as AIConfigRequest }),
    onSuccess: (status) => {
      queryClient.setQueryData(keys.aiStatus, status);
      invalidateAI(queryClient);
    },
  });
}

export function useTestAI() {
  return useMutation({ mutationFn: () => api.post('/ai/test') });
}

export function useRemoveAI() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete('/ai'),
    onSuccess: (status) => {
      queryClient.setQueryData(keys.aiStatus, status);
      invalidateAI(queryClient);
    },
  });
}

export function useSyncSettings() {
  return useQuery({
    queryKey: keys.syncSettings,
    queryFn: ({ signal }) => api.get('/settings/sync', { signal }),
  });
}

export function useSaveSyncSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (interval_minutes: number) => api.put('/settings/sync', { body: { interval_minutes } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(keys.syncSettings, saved);
      void queryClient.invalidateQueries({ queryKey: keys.syncStatus });
    },
  });
}

export function useSyncRuns(limit: number, poll: boolean) {
  return useQuery({
    queryKey: [...keys.syncRuns, limit] as const,
    queryFn: ({ signal }) => api.get('/sync/runs', { query: { limit }, signal }),
    refetchInterval: poll ? SYNC_POLL_RUNNING_MS : false,
  });
}

export function useDroppedCount() {
  return useQuery({
    queryKey: ['debug', 'dropped', 'count'] as const,
    queryFn: ({ signal }) => api.get('/debug/dropped', { query: { limit: 1 }, signal }),
  });
}

export function useClearDropped() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete('/debug/dropped'),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['debug', 'dropped'] }),
  });
}

export function useDeleteAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/data/delete-all', { body: { confirm: 'DELETE' } }),
    onSuccess: () => queryClient.clear(),
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'] as const,
    queryFn: ({ signal }) => api.get('/health', { signal }),
    staleTime: Infinity,
  });
}

export function useEstimate() {
  return useMutation({
    mutationFn: (body: { since_date: string; max_messages: number }) => api.post('/ai/estimate', { body }),
  });
}

export function useStartFirstSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { since_date: string; max_messages: number }) => api.post('/applications/sync', { body }),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: keys.syncStatus }),
  });
}

const overviewKey = ['analytics', 'overview'] as const;
const roleGroupsKey = ['analytics', 'role-groups'] as const;

function invalidateRoleGroups(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: overviewKey });
  return queryClient.invalidateQueries({ queryKey: roleGroupsKey });
}

/** Every role group, all time, for "Merge into…" and "Count as". */
export function useRoleGroups(enabled = true) {
  return useQuery({
    queryKey: roleGroupsKey,
    queryFn: ({ signal }) => api.get('/analytics/role-groups', { signal }),
    enabled,
  });
}

export function useMergeRoleGroups() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { source: string; target: string }) => api.post('/analytics/role-groups/merge', { body }),
    onSettled: () => invalidateRoleGroups(queryClient),
  });
}

export function useUndoRoleGroupMerge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (source: string) => api.delete('/analytics/role-groups/merge', { query: { source } }),
    onSettled: () => invalidateRoleGroups(queryClient),
  });
}

/** Merges proposed by the user's AI. Nothing changes until one is accepted. */
export function useSuggestRoleGroups() {
  return useMutation({
    mutationFn: () => api.post('/analytics/role-groups/suggest'),
  });
}

/** "Count as" for one application. Empty goes back to the role's own group. */
export function useCountAs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, group }: { id: string; group: string }) =>
      api.patch('/applications/{application_id}/metadata', {
        path: { application_id: id },
        body: { role_group_override: group },
      }),
    onSuccess: (updated) => {
      replaceInList(queryClient, updated);
      void invalidateRoleGroups(queryClient);
    },
  });
}
