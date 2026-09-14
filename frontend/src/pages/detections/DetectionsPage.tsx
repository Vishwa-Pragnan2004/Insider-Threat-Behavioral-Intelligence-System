import { Fragment, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Collapse,
  IconButton,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { KeyboardArrowDown, KeyboardArrowUp, Radar, Refresh } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import EmptyState from '../../components/common/EmptyState';
import { listDetectionCategories, listFindings } from '../../api/riskService';
import { apiErrorMessage } from '../../api/userService';
import type { Finding, FindingListParams } from '../../types/risk';
import { RiskScoreChip } from '../dashboards/shared';
import { CategoryChip, EmployeeLink, EvidenceToggle, formatDay } from '../risk/riskShared';

const ENGINES = [
  { value: 'behavioral', label: 'Behavioral' },
  { value: 'access', label: 'Access' },
  { value: 'data_exfiltration', label: 'Data exfiltration' },
  { value: 'privilege_abuse', label: 'Privilege abuse' },
];

const SEVERITY_FILTERS = [0, 20, 40, 60, 80];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

function engineLabel(engine: string): string {
  return ENGINES.find((e) => e.value === engine)?.label ?? engine;
}

/**
 * Detections
 *
 * Every finding produced by the category detectors, filterable and paged
 * server-side.
 */
export default function DetectionsPage() {
  const [category, setCategory] = useState('');
  const [engine, setEngine] = useState('');
  const [minSeverity, setMinSeverity] = useState(0);
  const [employee, setEmployee] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [expanded, setExpanded] = useState<string | null>(null);

  const debouncedEmployee = useDebouncedValue(employee.trim(), 400);

  // Any filter change goes back to the first page.
  useEffect(() => {
    setPage(0);
  }, [category, engine, minSeverity, debouncedEmployee, startDate, endDate]);

  const categoriesQuery = useQuery({
    queryKey: ['detections', 'categories'],
    queryFn: listDetectionCategories,
    staleTime: 10 * 60_000,
  });

  const params: FindingListParams = useMemo(
    () => ({
      ...(category && { category }),
      ...(engine && { engine }),
      ...(minSeverity > 0 && { min_severity: minSeverity }),
      ...(debouncedEmployee && { user_id: debouncedEmployee }),
      ...(startDate && { start: `${startDate}T00:00:00Z` }),
      ...(endDate && { end: `${endDate}T23:59:59Z` }),
      skip: page * rowsPerPage,
      limit: rowsPerPage,
    }),
    [category, engine, minSeverity, debouncedEmployee, startDate, endDate, page, rowsPerPage],
  );

  const query = useQuery({
    queryKey: ['detections', 'findings', params],
    queryFn: () => listFindings(params),
    placeholderData: (prev) => prev,
  });

  const categories = (categoriesQuery.data ?? []).filter((c) => !engine || c.engine === engine);
  const hasFilters = !!(category || engine || minSeverity || employee || startDate || endDate);

  const clearFilters = () => {
    setCategory('');
    setEngine('');
    setMinSeverity(0);
    setEmployee('');
    setStartDate('');
    setEndDate('');
  };

  const findings: Finding[] = query.data?.findings ?? [];

  return (
    <Box>
      <PageHeader
        title="Detections"
        subtitle="Findings from the anomaly detection engine, newest day first"
        actions={
          <Button
            startIcon={query.isFetching ? <CircularProgress size={16} /> : <Refresh />}
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            variant="outlined"
            size="small"
          >
            Refresh
          </Button>
        }
      />

      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <TextField
          select
          size="small"
          label="Engine"
          value={engine}
          onChange={(e) => {
            setEngine(e.target.value);
            setCategory('');
          }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          {ENGINES.map((e) => (
            <MenuItem key={e.value} value={e.value}>
              {e.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">All</MenuItem>
          {categories.map((c) => (
            <MenuItem key={c.category} value={c.category}>
              {c.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Min severity"
          value={minSeverity}
          onChange={(e) => setMinSeverity(Number(e.target.value))}
          sx={{ minWidth: 130 }}
        >
          {SEVERITY_FILTERS.map((s) => (
            <MenuItem key={s} value={s}>
              {s === 0 ? 'Any' : `≥ ${s}`}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Employee"
          placeholder="Exact user ID, e.g. DOMAIN\user"
          value={employee}
          onChange={(e) => setEmployee(e.target.value)}
          sx={{ minWidth: 220 }}
        />
        <TextField
          size="small"
          type="date"
          label="From"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          size="small"
          type="date"
          label="To"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        {hasFilters && (
          <Button size="small" onClick={clearFilters}>
            Clear
          </Button>
        )}
      </Box>

      <Box sx={{ bgcolor: 'background.paper', borderRadius: 2, overflow: 'hidden' }}>
        {query.isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : query.isError ? (
          <Alert severity="error" sx={{ m: 2 }}>
            Failed to load findings: {apiErrorMessage(query.error)}
          </Alert>
        ) : findings.length === 0 ? (
          <EmptyState
            icon={<Radar sx={{ fontSize: 56 }} />}
            title="No findings"
            description={
              hasFilters
                ? 'No findings match the current filters.'
                : 'Findings appear once the detection pipeline has run on collected activity.'
            }
          />
        ) : (
          <>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox" />
                    <TableCell>Day</TableCell>
                    <TableCell>Employee</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>Engine</TableCell>
                    <TableCell align="center">Severity</TableCell>
                    <TableCell>Title</TableCell>
                    <TableCell>Description</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {findings.map((f) => {
                    const open = expanded === f.id;
                    return (
                      <Fragment key={f.id}>
                        <TableRow hover sx={{ '& > td': { borderBottom: open ? 'none' : undefined } }}>
                          <TableCell padding="checkbox">
                            <IconButton size="small" onClick={() => setExpanded(open ? null : f.id)}>
                              {open ? <KeyboardArrowUp fontSize="small" /> : <KeyboardArrowDown fontSize="small" />}
                            </IconButton>
                          </TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDay(f.day)}</TableCell>
                          <TableCell>
                            <EmployeeLink userId={f.user_id} />
                          </TableCell>
                          <TableCell>
                            <CategoryChip label={f.category_label || f.category} />
                          </TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{engineLabel(f.engine)}</TableCell>
                          <TableCell align="center">
                            <RiskScoreChip score={f.severity} />
                          </TableCell>
                          <TableCell sx={{ fontWeight: 600, minWidth: 180 }}>{f.title}</TableCell>
                          <TableCell sx={{ maxWidth: 360 }}>
                            <Typography variant="body2" color="text.secondary" noWrap={!open}>
                              {f.description}
                            </Typography>
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell colSpan={8} sx={{ py: 0, borderBottom: open ? undefined : 'none' }}>
                            <Collapse in={open} unmountOnExit>
                              <Box sx={{ py: 1.5 }}>
                                <Typography variant="body2" sx={{ mb: 1 }}>
                                  {f.description}
                                </Typography>
                                <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mb: 0.5 }}>
                                  {f.detector} v{f.detector_version} · {f.event_ids.length} event(s)
                                </Typography>
                                <EvidenceToggle evidence={f.evidence} eventIds={f.event_ids} />
                              </Box>
                            </Collapse>
                          </TableCell>
                        </TableRow>
                      </Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </Box>
            <TablePagination
              component="div"
              count={query.data?.total ?? 0}
              page={page}
              onPageChange={(_, p) => setPage(p)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value, 10));
                setPage(0);
              }}
              rowsPerPageOptions={[10, 25, 50, 100]}
            />
          </>
        )}
      </Box>
    </Box>
  );
}
