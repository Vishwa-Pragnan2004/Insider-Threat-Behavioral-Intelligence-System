/**
 * Employee Directory Service
 * Links monitored accounts and devices to employees.
 *
 * Employee IDs, accounts and device IDs may contain characters such as "\" or
 * "@", so every path segment is encoded.
 */
import { apiClient } from '../services/apiClient';
import type {
  AccountType,
  Employee,
  EmployeeCreateRequest,
  EmployeeImportResult,
  EmployeeList,
  EmployeeListParams,
  EmployeeUpdateRequest,
  UnmappedAccountList,
} from '../types/employees';

const seg = encodeURIComponent;

/** Sorted by name. Needs employees:read. */
export async function listEmployees(params: EmployeeListParams = {}): Promise<EmployeeList> {
  const { data } = await apiClient.get<EmployeeList>('/employees', { params });
  return data;
}

/** 404 for an unknown employee. Needs employees:read. */
export async function getEmployee(employeeId: string): Promise<Employee> {
  const { data } = await apiClient.get<Employee>(`/employees/${seg(employeeId)}`);
  return data;
}

/** Accounts seen in ingested events that no employee owns. Needs employees:read. */
export async function listUnmappedAccounts(days = 30): Promise<UnmappedAccountList> {
  const { data } = await apiClient.get<UnmappedAccountList>('/employees/unmapped-accounts', {
    params: { days },
  });
  return data;
}

/** 409 on a duplicate employee_id. Needs employees:manage. */
export async function createEmployee(body: EmployeeCreateRequest): Promise<Employee> {
  const { data } = await apiClient.post<Employee>('/employees', body);
  return data;
}

export async function updateEmployee(employeeId: string, body: EmployeeUpdateRequest): Promise<Employee> {
  const { data } = await apiClient.patch<Employee>(`/employees/${seg(employeeId)}`, body);
  return data;
}

/** 409 if the account already belongs to another employee. */
export async function addEmployeeAccount(
  employeeId: string,
  account: string,
  accountType: AccountType = 'windows',
): Promise<Employee> {
  const { data } = await apiClient.post<Employee>(`/employees/${seg(employeeId)}/accounts`, {
    account,
    account_type: accountType,
  });
  return data;
}

export async function removeEmployeeAccount(employeeId: string, accountId: string): Promise<Employee> {
  const { data } = await apiClient.delete<Employee>(
    `/employees/${seg(employeeId)}/accounts/${seg(accountId)}`,
  );
  return data;
}

/** 409 if the device is assigned to another employee. */
export async function addEmployeeDevice(
  employeeId: string,
  deviceId: string,
  dedicated = true,
): Promise<Employee> {
  const { data } = await apiClient.post<Employee>(`/employees/${seg(employeeId)}/devices`, {
    device_id: deviceId,
    dedicated,
  });
  return data;
}

export async function removeEmployeeDevice(employeeId: string, deviceUuid: string): Promise<Employee> {
  const { data } = await apiClient.delete<Employee>(
    `/employees/${seg(employeeId)}/devices/${seg(deviceUuid)}`,
  );
  return data;
}

/** ITBIS CSV or a CERT LDAP export. 422 on unrecognised columns. */
export async function importEmployees(file: File): Promise<EmployeeImportResult> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await apiClient.post<EmployeeImportResult>('/employees/import', form, {
    // Overrides the client's JSON default; the browser adds the boundary.
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  });
  return data;
}
