/**
 * ITBIS — Employee Directory Types
 * Mirror GET/POST/PATCH/DELETE /api/v1/employees/*.
 */

export type EmployeeStatus = 'ACTIVE' | 'LEFT';
export type AccountType = 'windows' | 'email' | 'dataset' | 'other';

export const ACCOUNT_TYPES: AccountType[] = ['windows', 'email', 'dataset', 'other'];

export interface EmployeeAccount {
  id: string;
  account: string;
  account_type: AccountType;
}

export interface EmployeeDevice {
  id: string;
  device_id: string;
  dedicated: boolean;
}

export interface Employee {
  id: string;
  employee_id: string;
  full_name: string;
  email: string | null;
  department: string;
  job_title: string;
  team: string;
  manager_employee_id: string | null;
  status: EmployeeStatus;
  privileged: boolean;
  accounts: EmployeeAccount[];
  devices: EmployeeDevice[];
  created_at: string;
  updated_at: string;
}

export interface EmployeeList {
  employees: Employee[];
  total: number;
  skip: number;
  limit: number;
}

export interface EmployeeListParams {
  search?: string;
  department?: string;
  status?: EmployeeStatus;
  skip?: number;
  /** ≤ 500 */
  limit?: number;
}

export interface EmployeeCreateRequest {
  employee_id: string;
  full_name: string;
  email?: string | null;
  department?: string;
  job_title?: string;
  team?: string;
  manager_employee_id?: string | null;
  status?: EmployeeStatus;
  privileged?: boolean;
}

export type EmployeeUpdateRequest = Partial<Omit<EmployeeCreateRequest, 'employee_id'>>;

export interface UnmappedAccount {
  account: string;
  events: number;
  devices: string[];
  last_seen: string | null;
}

export interface UnmappedAccountList {
  days: number;
  accounts: UnmappedAccount[];
}

export interface EmployeeImportResult {
  format: 'itbis' | 'cert_ldap';
  created: number;
  updated: number;
  accounts_linked: number;
  devices_linked: number;
  skipped: number;
  errors: string[];
}
