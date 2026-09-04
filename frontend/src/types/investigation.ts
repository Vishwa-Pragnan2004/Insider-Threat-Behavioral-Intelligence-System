/**
 * ITBIS — Investigation Types
 * Aligned with backend app/modules/investigations/application/dtos.py
 */

export type { InvestigationStatus } from './index';

export interface Investigation {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  created_by: string;
  assigned_to: string | null;
  related_alert_ids: string[];
  related_user_ids: string[];
  resolution: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface InvestigationListResponse {
  investigations: Investigation[];
  count: number;
  total: number;
  skip: number;
  limit: number;
}

export interface InvestigationListParams {
  status?: string;
  assigned_to?: string;
  severity?: string;
  related_user_id?: string;
  created_by?: string;
  skip?: number;
  limit?: number;
}

export interface InvestigationCreateRequest {
  title: string;
  description?: string;
  severity?: string;
  related_alert_ids?: string[];
  related_user_ids?: string[];
  assigned_to?: string | null;
}

export interface InvestigationAssignRequest {
  user_id: string;
}

export interface InvestigationStatusRequest {
  status: string;
  resolution?: string | null;
}

export interface InvestigationAddAlertRequest {
  alert_id: string;
  user_id?: string | null;
}

export interface Note {
  id: string;
  investigation_id: string;
  author_id: string;
  content: string;
  created_at: string;
}

export interface NoteListResponse {
  investigation_id: string;
  notes: Note[];
  count: number;
}

export interface NoteCreateRequest {
  content: string;
}
