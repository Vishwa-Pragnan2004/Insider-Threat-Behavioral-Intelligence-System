/**
 * Investigation Service
 * All calls use the canonical apiClient with auto token attachment.
 */
import { apiClient } from '../services/apiClient';
import type {
  Investigation,
  InvestigationListResponse,
  InvestigationListParams,
  InvestigationCreateRequest,
  InvestigationAssignRequest,
  InvestigationStatusRequest,
  InvestigationAddAlertRequest,
  NoteListResponse,
  NoteCreateRequest,
  Note,
} from '../types/investigation';

export async function listInvestigations(params: InvestigationListParams = {}): Promise<InvestigationListResponse> {
  const { data } = await apiClient.get<InvestigationListResponse>('/investigations/', { params });
  return data;
}

export async function getInvestigation(investigationId: string): Promise<Investigation> {
  const { data } = await apiClient.get<Investigation>(`/investigations/${investigationId}`);
  return data;
}

export async function createInvestigation(body: InvestigationCreateRequest): Promise<Investigation> {
  const { data } = await apiClient.post<Investigation>('/investigations/', body);
  return data;
}

export async function assignInvestigation(investigationId: string, body: InvestigationAssignRequest): Promise<Investigation> {
  const { data } = await apiClient.post<Investigation>(`/investigations/${investigationId}/assign`, body);
  return data;
}

export async function updateInvestigationStatus(investigationId: string, body: InvestigationStatusRequest): Promise<Investigation> {
  const { data } = await apiClient.post<Investigation>(`/investigations/${investigationId}/status`, body);
  return data;
}

export async function linkAlertToInvestigation(investigationId: string, body: InvestigationAddAlertRequest): Promise<Investigation> {
  const { data } = await apiClient.post<Investigation>(`/investigations/${investigationId}/alerts`, body);
  return data;
}

export async function unlinkAlertFromInvestigation(investigationId: string, alertId: string): Promise<Investigation> {
  const { data } = await apiClient.delete<Investigation>(`/investigations/${investigationId}/alerts/${alertId}`);
  return data;
}

export async function listNotes(investigationId: string): Promise<NoteListResponse> {
  const { data } = await apiClient.get<NoteListResponse>(`/investigations/${investigationId}/notes`);
  return data;
}

export async function addNote(investigationId: string, body: NoteCreateRequest): Promise<Note> {
  const { data } = await apiClient.post<Note>(`/investigations/${investigationId}/notes`, body);
  return data;
}
