import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Chip, Collapse, Link, Tooltip, Typography } from '@mui/material';
import { ArrowDropDown, ArrowDropUp } from '@mui/icons-material';
import { getRiskModel } from '../../api/riskService';
import type { EmployeeRisk, RiskModel, RiskModelComponent } from '../../types/risk';
import { NO_VALUE, RISK_COLORS } from '../dashboards/shared';

/**
 * Building blocks shared by the insider risk, employee detail and detection
 * pages (and the analyst dashboard's risk table).
 */

// ─── Model ────────────────────────────────────────────────────

/** Used until GET /risk/model answers (or if it fails), so the UI never blanks. */
export const DEFAULT_RISK_COMPONENTS: RiskModelComponent[] = [
  { component: 'behavioral_anomalies', label: 'Behavioral anomalies', weight: 0.35 },
  { component: 'privilege_misuse', label: 'Privilege misuse', weight: 0.25 },
  { component: 'data_access_violations', label: 'Data access violations', weight: 0.2 },
  { component: 'access_pattern_deviations', label: 'Access pattern deviations', weight: 0.1 },
  { component: 'historical_security_events', label: 'Historical security events', weight: 0.1 },
];

export const DEFAULT_ALERT_MIN_PRIORITY = 60;

export const COMPONENT_COLORS: Record<string, string> = {
  behavioral_anomalies: '#8b5cf6',
  privilege_misuse: '#ef4444',
  data_access_violations: '#f97316',
  access_pattern_deviations: '#3b82f6',
  historical_security_events: '#14b8a6',
};

export function componentColor(component: string): string {
  return COMPONENT_COLORS[component] ?? '#64748b';
}

/** Pass enabled=false where the viewer may lack anomaly:read; helpers fall back to the default model. */
export function useRiskModel(enabled = true) {
  return useQuery({
    queryKey: ['risk', 'model'],
    queryFn: getRiskModel,
    staleTime: 10 * 60_000,
    enabled,
  });
}

/**
 * Model components with weights as fractions (0–1). Accepts weights sent as
 * either fractions (0.35) or percentages (35).
 */
export function modelComponents(model: RiskModel | undefined): RiskModelComponent[] {
  const components = model?.components?.length ? model.components : DEFAULT_RISK_COMPONENTS;
  const total = components.reduce((sum, c) => sum + c.weight, 0);
  const scale = total > 1.5 ? 100 : 1;
  return components.map((c) => ({ ...c, weight: c.weight / scale }));
}

export function componentLabel(model: RiskModel | undefined, component: string | null | undefined): string {
  if (!component) return NO_VALUE;
  return modelComponents(model).find((c) => c.component === component)?.label ?? component.replace(/_/g, ' ');
}

export function weightPct(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

// ─── Links ────────────────────────────────────────────────────

export function employeeRiskPath(userId: string): string {
  return `/risk/${encodeURIComponent(userId)}`;
}

export function EmployeeLink({ userId }: { userId: string }) {
  return (
    <Link
      component={RouterLink}
      to={employeeRiskPath(userId)}
      underline="hover"
      sx={{ fontFamily: 'monospace', fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap' }}
    >
      {userId}
    </Link>
  );
}

// ─── Indicators ───────────────────────────────────────────────

/** ▲ red when risk is rising, ▼ green when falling. */
export function TrendIndicator({ trend }: { trend: number | null | undefined }) {
  if (trend === null || trend === undefined) {
    return <Typography variant="body2" color="text.disabled">{NO_VALUE}</Typography>;
  }
  const rising = trend > 0;
  const flat = Math.abs(trend) < 0.05;
  const color = flat ? 'text.secondary' : rising ? RISK_COLORS.CRITICAL : RISK_COLORS.LOW;
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', color, fontWeight: 600, fontSize: '0.85rem', whiteSpace: 'nowrap' }}>
      {!flat && (rising ? <ArrowDropUp fontSize="small" /> : <ArrowDropDown fontSize="small" />)}
      {flat ? '0.0' : `${rising ? '+' : ''}${trend.toFixed(1)}`}
    </Box>
  );
}

/** Compact stacked bar of weight × component value; full width equals a score of 100. */
export function ContributionBar({
  components,
  model,
  width = 160,
}: {
  components: EmployeeRisk['components'];
  model: RiskModel | undefined;
  width?: number;
}) {
  const parts = modelComponents(model).map((c) => ({
    ...c,
    value: components?.[c.component] ?? 0,
    contribution: c.weight * (components?.[c.component] ?? 0),
  }));
  const tooltip = (
    <Box>
      {parts.map((p) => (
        <Box key={p.component} sx={{ display: 'flex', alignItems: 'center', gap: 1, fontSize: '0.75rem' }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '2px', bgcolor: componentColor(p.component) }} />
          <span>
            {p.label}: {p.value.toFixed(0)} × {weightPct(p.weight)} = {p.contribution.toFixed(1)}
          </span>
        </Box>
      ))}
    </Box>
  );
  return (
    <Tooltip title={tooltip} arrow>
      <Box
        sx={{
          display: 'flex',
          width,
          height: 10,
          borderRadius: 1,
          overflow: 'hidden',
          bgcolor: 'rgba(148,163,184,0.15)',
        }}
      >
        {parts.map((p) =>
          p.contribution > 0 ? (
            <Box
              key={p.component}
              sx={{ width: `${Math.min(p.contribution, 100)}%`, bgcolor: componentColor(p.component) }}
            />
          ) : null,
        )}
      </Box>
    </Tooltip>
  );
}

export function CategoryChip({ label }: { label: string }) {
  return (
    <Chip
      size="small"
      label={label}
      variant="outlined"
      sx={{ fontSize: '0.7rem', height: 22, borderColor: 'divider', color: 'text.secondary' }}
    />
  );
}

export function categoryLabel(category: string, labels?: Record<string, string>): string {
  return labels?.[category] ?? category.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

/** Collapsible pretty-printed JSON evidence. */
export function EvidenceToggle({ evidence, eventIds }: { evidence: Record<string, unknown>; eventIds?: string[] }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = evidence && Object.keys(evidence).length > 0;
  if (!hasEvidence && !eventIds?.length) return null;
  return (
    <Box>
      <Link component="button" type="button" variant="caption" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide evidence' : 'Show evidence'}
      </Link>
      <Collapse in={open} unmountOnExit>
        <Box
          component="pre"
          sx={{
            mt: 1,
            p: 1.5,
            bgcolor: 'background.default',
            borderRadius: 1,
            fontSize: '0.75rem',
            overflowX: 'auto',
            maxHeight: 320,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {JSON.stringify(hasEvidence ? evidence : {}, null, 2)}
          {eventIds?.length ? `\n\nevent_ids: ${eventIds.join(', ')}` : ''}
        </Box>
      </Collapse>
    </Box>
  );
}

export function formatDay(day: string | null | undefined): string {
  if (!day) return NO_VALUE;
  // YYYY-MM-DD is rendered as a calendar date, without a timezone shift.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day.slice(0, 10));
  if (!m) return day;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).toLocaleDateString();
}
