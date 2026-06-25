/**
 * RecurrencePatternSelector component.
 *
 * Provides UI for selecting and configuring recurring schedules for scheduled reports.
 * Includes predefined patterns (Daily, Weekday, Weekly, Monthly, Custom) with time
 * and timezone selectors. Emits RecurrencePattern objects on change.
 *
 * Features:
 * - 8 predefined pattern options
 * - 24-hour time selector (hour + minute)
 * - IANA timezone selector with common presets
 * - Custom interval mode for flexible scheduling
 * - Day-of-week and day-of-month constraints for custom patterns
 *
 * Requirements: 5.1, 5.2, 5.6
 */

import { useCallback, useMemo } from 'react';
import type { RecurrencePattern } from '../types/scheduledReports';

export interface RecurrencePatternSelectorProps {
  /** Current pattern value */
  value: RecurrencePattern;
  /** Callback fired when pattern changes */
  onChange: (pattern: RecurrencePattern) => void;
  /** Optional CSS class for the root container */
  className?: string;
}

/**
 * Common IANA timezone names, sorted alphabetically.
 * These are the most commonly used timezones for business reporting.
 */
const COMMON_TIMEZONES = [
  'Asia/Kolkata',
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Tokyo',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Australia/Sydney',
];

/**
 * Day names for display and selection
 */
const DAYS_OF_WEEK = [
  { label: 'Sunday', value: 0 },
  { label: 'Monday', value: 1 },
  { label: 'Tuesday', value: 2 },
  { label: 'Wednesday', value: 3 },
  { label: 'Thursday', value: 4 },
  { label: 'Friday', value: 5 },
  { label: 'Saturday', value: 6 },
];

/**
 * Predefined pattern templates
 */
const PREDEFINED_PATTERNS = [
  { label: 'Daily', type: 'daily' as const },
  { label: 'Every weekday (Mon-Fri)', type: 'weekday' as const },
  { label: 'Every Saturday', type: 'weekly' as const, day: 6 },
  { label: 'Every Sunday', type: 'weekly' as const, day: 0 },
  { label: '1st of month', type: 'monthly' as const, day: 1 },
  { label: '15th of month', type: 'monthly' as const, day: 15 },
  { label: 'Custom', type: 'custom' as const },
];

export function RecurrencePatternSelector({
  value,
  onChange,
  className = '',
}: RecurrencePatternSelectorProps) {
  /**
   * Handle predefined pattern selection
   */
  const handleSelectPredefined = useCallback(
    (pattern: RecurrencePattern) => {
      const updated = { ...value, ...pattern };
      onChange(updated);
    },
    [value, onChange],
  );

  /**
   * Handle time hour change (0-23)
   */
  const handleHourChange = useCallback(
    (newHour: number) => {
      onChange({ ...value, time_hour: newHour });
    },
    [value, onChange],
  );

  /**
   * Handle time minute change (0-59)
   */
  const handleMinuteChange = useCallback(
    (newMinute: number) => {
      onChange({ ...value, time_minute: newMinute });
    },
    [value, onChange],
  );

  /**
   * Handle timezone change
   */
  const handleTimezoneChange = useCallback(
    (newTimezone: string) => {
      onChange({ ...value, timezone: newTimezone });
    },
    [value, onChange],
  );

  /**
   * Handle custom interval change
   */
  const handleCustomIntervalChange = useCallback(
    (newInterval: number) => {
      onChange({ ...value, custom_interval: newInterval });
    },
    [value, onChange],
  );

  /**
   * Handle custom unit change
   */
  const handleCustomUnitChange = useCallback(
    (newUnit: 'days' | 'weeks' | 'months') => {
      onChange({ ...value, custom_unit: newUnit });
    },
    [value, onChange],
  );

  /**
   * Handle day-of-week change for custom patterns
   */
  const handleDayOfWeekChange = useCallback(
    (newDay: number) => {
      onChange({ ...value, day_of_week: newDay });
    },
    [value, onChange],
  );

  /**
   * Handle day-of-month change for custom patterns
   */
  const handleDayOfMonthChange = useCallback(
    (newDay: number) => {
      onChange({ ...value, day_of_month: newDay });
    },
    [value, onChange],
  );

  /**
   * Generate array of hours (0-23)
   */
  const hours = useMemo(() => Array.from({ length: 24 }, (_, i) => i), []);

  /**
   * Generate array of minutes (0-59)
   */
  const minutes = useMemo(() => Array.from({ length: 60 }, (_, i) => i), []);

  /**
   * Generate array of days of month (1-31)
   */
  const daysOfMonth = useMemo(() => Array.from({ length: 31 }, (_, i) => i + 1), []);

  /**
   * Format time display (0-23 → 00:00)
   */
  const formatTime = (hour: number, minute: number) => {
    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  };

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Predefined Patterns Grid */}
      <div>
        <label className="block text-sm font-medium text-text-primary mb-3">
          Recurrence Pattern
        </label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {PREDEFINED_PATTERNS.map((pattern, index) => (
            <button
              key={`pattern-${index}`}
              type="button"
              onClick={() => {
                const basePattern: RecurrencePattern = {
                  type: pattern.type,
                  time_hour: value.time_hour,
                  time_minute: value.time_minute,
                  timezone: value.timezone,
                };
                if (pattern.day !== undefined && pattern.type === 'weekly') {
                  basePattern.day_of_week = pattern.day;
                }
                if (pattern.day !== undefined && pattern.type === 'monthly') {
                  basePattern.day_of_month = pattern.day;
                }
                handleSelectPredefined(basePattern);
              }}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                value.type === pattern.type &&
                ((pattern.type === 'weekly' && value.day_of_week === pattern.day) ||
                  (pattern.type === 'monthly' && value.day_of_month === pattern.day) ||
                  (pattern.type !== 'weekly' && pattern.type !== 'monthly'))
                  ? 'bg-accent-primary text-white'
                  : 'bg-bg-input text-text-secondary hover:bg-bg-secondary'
              }`}
            >
              {pattern.label}
            </button>
          ))}
        </div>
      </div>

      {/* Time Selector */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        {/* Hour Selector */}
        <div>
          <label htmlFor="hour-select" className="block text-sm font-medium text-text-primary mb-2">
            Hour (24h)
          </label>
          <select
            id="hour-select"
            value={value.time_hour}
            onChange={(e) => handleHourChange(parseInt(e.target.value, 10))}
            className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            {hours.map((h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, '0')}
              </option>
            ))}
          </select>
        </div>

        {/* Minute Selector */}
        <div>
          <label
            htmlFor="minute-select"
            className="block text-sm font-medium text-text-primary mb-2"
          >
            Minute
          </label>
          <select
            id="minute-select"
            value={value.time_minute}
            onChange={(e) => handleMinuteChange(parseInt(e.target.value, 10))}
            className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            {minutes.map((m) => (
              <option key={m} value={m}>
                {String(m).padStart(2, '0')}
              </option>
            ))}
          </select>
        </div>

        {/* Timezone Selector */}
        <div>
          <label
            htmlFor="timezone-select"
            className="block text-sm font-medium text-text-primary mb-2"
          >
            Timezone
          </label>
          <select
            id="timezone-select"
            value={value.timezone}
            onChange={(e) => handleTimezoneChange(e.target.value)}
            className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            {COMMON_TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Preview */}
      <div className="px-3 py-2 bg-accent-subtle border border-accent-primary/20 rounded-lg">
        <p className="text-sm text-text-secondary">
          <span className="font-medium">Preview:</span> {formatTime(value.time_hour, value.time_minute)}{' '}
          {value.timezone}
        </p>
      </div>

      {/* Custom Pattern Options */}
      {value.type === 'custom' && (
        <div className="space-y-4 pt-4 border-t border-border-default">
          <h3 className="text-sm font-medium text-text-primary">Custom Schedule</h3>

          {/* Interval + Unit */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="interval-input"
                className="block text-sm font-medium text-text-primary mb-2"
              >
                Every N
              </label>
              <input
                id="interval-input"
                type="number"
                min={1}
                max={365}
                value={value.custom_interval ?? 1}
                onChange={(e) => handleCustomIntervalChange(Math.max(1, parseInt(e.target.value, 10)))}
                className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
              />
            </div>

            <div>
              <label
                htmlFor="unit-select"
                className="block text-sm font-medium text-text-primary mb-2"
              >
                Unit
              </label>
              <select
                id="unit-select"
                value={value.custom_unit ?? 'days'}
                onChange={(e) => handleCustomUnitChange(e.target.value as 'days' | 'weeks' | 'months')}
                className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
              >
                <option value="days">Days</option>
                <option value="weeks">Weeks</option>
                <option value="months">Months</option>
              </select>
            </div>
          </div>

          {/* Day-of-week selector (for weekly patterns) */}
          {(value.custom_unit === 'weeks' || value.custom_unit === undefined) && (
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">
                On which day?
              </label>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {DAYS_OF_WEEK.map((day) => (
                  <button
                    key={day.value}
                    type="button"
                    onClick={() => handleDayOfWeekChange(day.value)}
                    className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                      value.day_of_week === day.value
                        ? 'bg-accent-primary text-white'
                        : 'bg-bg-input text-text-secondary hover:bg-bg-secondary'
                    }`}
                  >
                    {day.label.slice(0, 3)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Day-of-month selector (for monthly patterns) */}
          {value.custom_unit === 'months' && (
            <div>
              <label
                htmlFor="day-of-month-select"
                className="block text-sm font-medium text-text-primary mb-2"
              >
                On which day of the month?
              </label>
              <select
                id="day-of-month-select"
                value={value.day_of_month ?? 1}
                onChange={(e) => handleDayOfMonthChange(parseInt(e.target.value, 10))}
                className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
              >
                {daysOfMonth.map((d) => (
                  <option key={d} value={d}>
                    Day {d}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
