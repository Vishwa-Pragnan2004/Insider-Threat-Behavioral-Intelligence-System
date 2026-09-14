import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Chip, Link } from '@mui/material';
import { AdminPanelSettings } from '@mui/icons-material';
import { listEmployees } from '../../api/employeeService';
import type { AccountType, Employee, EmployeeStatus } from '../../types/employees';

/**
 * Building blocks shared by the employee directory pages and the insider risk
 * page's name lookup.
 */

export const EMPLOYEE_ID_PATTERN = /^[A-Za-z0-9._@\\-]+$/;
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function employeePath(employeeId: string): string {
  return `/employees/${encodeURIComponent(employeeId)}`;
}

/** Route params may arrive still percent-encoded depending on the router version. */
export function decodeParam(value: string | undefined): string {
  if (!value) return '';
  if (!/%[0-9A-Fa-f]{2}/.test(value)) return value;
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

/** "@" → email, "\" → windows, anything else is assumed to be a dataset id. */
export function guessAccountType(account: string): AccountType {
  if (account.includes('@')) return 'email';
  if (account.includes('\\')) return 'windows';
  return 'dataset';
}

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  windows: 'Windows',
  email: 'Email',
  dataset: 'Dataset',
  other: 'Other',
};

/** The account insider risk is keyed on: first windows, else dataset, else email. */
export function primaryAccount(employee: Employee): string | null {
  for (const type of ['windows', 'dataset', 'email'] as AccountType[]) {
    const match = employee.accounts.find((a) => a.account_type === type);
    if (match) return match.account;
  }
  return null;
}

export function StatusChip({ status }: { status: EmployeeStatus }) {
  const active = status === 'ACTIVE';
  return (
    <Chip
      size="small"
      label={active ? 'Active' : 'Left'}
      color={active ? 'success' : 'default'}
      variant={active ? 'filled' : 'outlined'}
    />
  );
}

export function PrivilegedChip() {
  return (
    <Chip
      size="small"
      icon={<AdminPanelSettings />}
      label="Privileged"
      color="warning"
      variant="outlined"
    />
  );
}

export function EmployeeNameLink({ employee }: { employee: Pick<Employee, 'employee_id' | 'full_name'> }) {
  return (
    <Link component={RouterLink} to={employeePath(employee.employee_id)} underline="hover">
      {employee.full_name || employee.employee_id}
    </Link>
  );
}

/**
 * Account (lower-cased) → employee, from the first 500 directory entries.
 * Cached for five minutes; pass enabled=false when the viewer lacks employees:read.
 */
export function useEmployeeAccountIndex(enabled: boolean) {
  const query = useQuery({
    queryKey: ['employees', 'directory-index'],
    queryFn: () => listEmployees({ limit: 500 }),
    staleTime: 5 * 60_000,
    enabled,
    retry: false,
  });
  return useMemo(() => {
    const index = new Map<string, Employee>();
    for (const employee of query.data?.employees ?? []) {
      for (const a of employee.accounts) index.set(a.account.toLowerCase(), employee);
    }
    return index;
  }, [query.data]);
}
