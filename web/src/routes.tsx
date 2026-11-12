import { QueryClient } from '@tanstack/react-query';
import { Navigate, type RouteObject } from 'react-router-dom';
import { ApiError } from './api/client';
import { Layout } from './components/Layout';
import { ApplicationsPage } from './pages/applications/ApplicationsPage';
import { NotFoundPage } from './pages/Placeholder';
import { SettingsPage } from './pages/settings/SettingsPage';
import { SetupPage } from './pages/setup/SetupPage';
import { AnalyticsPage } from './pages/analytics/AnalyticsPage';
import { NotificationsPage } from './pages/notifications/NotificationsPage';
import { OpportunitiesPage } from './pages/opportunities/OpportunitiesPage';
import { NeedsReviewPage } from './pages/review/NeedsReviewPage';

export const routes: RouteObject[] = [
  { path: 'setup', element: <SetupPage /> },
  {
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/applications" replace /> },
      { path: 'applications', element: <ApplicationsPage /> },
      { path: 'review', element: <NeedsReviewPage /> },
      { path: 'opportunities', element: <OpportunitiesPage /> },
      { path: 'analytics', element: <AnalyticsPage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failures < 2,
      },
    },
  });
}
