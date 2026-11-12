import type { components } from './schema';

type Schemas = components['schemas'];

export type Application = Schemas['ApplicationResponse'];
export type ApplicationCreate = Schemas['ApplicationCreate'];
export type ApplicationUpdate = Schemas['ApplicationUpdate'];
export type ApplicationMetadataUpdate = Schemas['ApplicationMetadataUpdate'];
export type TimelineEvent = Schemas['TimelineEvent'];
export type SyncStatus = Schemas['SyncStatusResponse'];
export type SyncRun = Schemas['SyncRunResponse'];
export type MailStatus = Schemas['MailStatusResponse'];
export type Opportunity = Schemas['OpportunityResponse'];
export type Today = Schemas['TodayResponse'];
export type AttentionItem = Schemas['AttentionItem'];
export type InterviewOutcome = Schemas['InterviewOutcome']['outcome'];
export type EmailContent = Schemas['EmailContent'];
export type AIStatus = Schemas['AIStatusResponse'];
export type AIReviewResult = Schemas['AIReviewResponse'];
export type AnalyticsOverview = Schemas['AnalyticsOverview'];
export type WeeklyReview = Schemas['WeeklyReview'];
export type Notification = Schemas['NotificationResponse'];
export type AIProvider = Schemas['ProviderInfo'];
export type AIModel = Schemas['ModelInfo'];
export type AIConfigRequest = Schemas['AIConfigRequest'];
export type SetupStatus = Schemas['SetupStatusResponse'];
export type Estimate = Schemas['EstimateResponse'];
export type RateRow = Schemas['RateRow'];
export type RoleGroupRow = Schemas['RoleGroupRow'];
export type RoleGroups = Schemas['RoleGroups'];
export type RoleGroupSuggestion = Schemas['Suggestion'];
export type AnalyticsRange = AnalyticsOverview['range'];

export const BOARD_STATUSES = ['Applied', 'Assessment', 'Interview', 'Offer', 'Rejected'] as const;
export type BoardStatus = (typeof BOARD_STATUSES)[number];
export const NEEDS_REVIEW = 'Needs Review';

export const REVIEW_STATUSES = ['Applied', 'Assessment', 'Interview', 'Rejected', 'Offer'] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];
