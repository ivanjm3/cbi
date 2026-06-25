"""Recurrence calculator for scheduled reports.

This module provides timezone-aware computation of next execution times
for scheduled reports based on recurrence patterns. It supports daily,
weekday, weekly, monthly, and custom interval patterns.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.models.scheduled_reports import RecurrencePattern


def compute_next_execution(
    pattern: RecurrencePattern,
    after: datetime,
    timezone_str: str,
) -> datetime:
    """Compute the next execution time given a recurrence pattern.
    
    Args:
        pattern: RecurrencePattern object specifying the schedule
        after: Compute next run after this datetime (expected UTC or timezone-aware)
        timezone_str: IANA timezone string (e.g., "America/New_York")
        
    Returns:
        datetime: Next execution time (timezone-aware, in the specified timezone)
        
    Raises:
        ValueError: If next execution is more than 30 days in future (non-custom patterns)
                   or if pattern is invalid
        
    Validates:
        - Result is strictly in the future
        - Result respects specified timezone
        - Result matches day_of_week/day_of_month constraints
        - Non-custom patterns: result within 30 days
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception as e:
        raise ValueError(f"Invalid timezone: {timezone_str}") from e
    
    # Normalize input datetime to the target timezone
    if after.tzinfo is None:
        # Assume UTC if naive
        after = after.replace(tzinfo=ZoneInfo("UTC"))
    
    # Convert to target timezone for calculation
    after_local = after.astimezone(tz)
    
    # Ensure we're computing a strictly future time
    # Advance by 1 second to get past the current moment
    candidate = after_local.replace(second=0, microsecond=0) + timedelta(seconds=1)
    
    if pattern.type == "daily":
        next_run = _compute_daily(candidate, pattern, tz)
    elif pattern.type == "weekday":
        next_run = _compute_weekday(candidate, pattern, tz)
    elif pattern.type == "weekly":
        next_run = _compute_weekly(candidate, pattern, tz)
    elif pattern.type == "monthly":
        next_run = _compute_monthly(candidate, pattern, tz)
    elif pattern.type == "custom":
        next_run = _compute_custom(candidate, pattern, tz)
    else:
        raise ValueError(f"Unknown recurrence type: {pattern.type}")
    
    # Verify result is strictly in the future
    if next_run <= after_local:
        raise ValueError(f"Computed next_run {next_run} is not after {after_local}")
    
    # Validate non-custom patterns don't exceed 30-day window
    if pattern.type != "custom":
        days_ahead = (next_run.date() - after_local.date()).days
        if days_ahead > 30:
            raise ValueError(
                f"Next execution for pattern type '{pattern.type}' is {days_ahead} days away, "
                f"exceeds maximum of 30 days"
            )
    
    return next_run


def _compute_daily(
    candidate: datetime,
    pattern: RecurrencePattern,
    tz: ZoneInfo,
) -> datetime:
    """Compute next daily execution.
    
    Matches the specified time_hour and time_minute every day.
    candidate is the current time (in target tz) plus 1 second.
    """
    # First, try today at the target time
    target_today = candidate.replace(hour=pattern.time_hour, minute=pattern.time_minute, second=0, microsecond=0)
    
    # If that's still in the future, use it
    if target_today >= candidate:
        return target_today
    
    # Otherwise, use tomorrow at the target time
    return target_today + timedelta(days=1)


def _compute_weekday(
    candidate: datetime,
    pattern: RecurrencePattern,
    tz: ZoneInfo,
) -> datetime:
    """Compute next weekday (Mon-Fri) execution.
    
    Matches the specified time_hour and time_minute on Monday-Friday.
    candidate is the current time (in target tz) plus 1 second.
    """
    # Check today and the next 6 days for a weekday at the target time
    for days_offset in range(7):
        test_date = candidate.replace(hour=pattern.time_hour, minute=pattern.time_minute, second=0, microsecond=0)
        test_date = test_date + timedelta(days=days_offset)
        
        # If it's a weekday (0=Monday, 4=Friday) and it's in the future, use it
        if test_date.weekday() < 5 and test_date >= candidate:
            return test_date
    
    # Should never reach here (at least one weekday in 7 days)
    raise ValueError("No future weekday found in next 7 days (should not happen)")


def _compute_weekly(
    candidate: datetime,
    pattern: RecurrencePattern,
    tz: ZoneInfo,
) -> datetime:
    """Compute next weekly execution.
    
    Matches the specified day_of_week and time_hour:time_minute.
    day_of_week: 0=Sunday, 6=Saturday
    candidate is the current time (in target tz) plus 1 second.
    """
    if pattern.day_of_week is None:
        raise ValueError("Weekly pattern requires day_of_week")
    
    # Convert pattern's day_of_week (0=Sunday, 6=Saturday) to Python's weekday (0=Monday, 6=Sunday)
    # Python: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    # Pattern: Sun=0, Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6
    # Formula: python_weekday = (pattern_day - 1) % 7
    target_weekday = (pattern.day_of_week - 1) % 7
    
    # Set to target time
    target_time = candidate.replace(hour=pattern.time_hour, minute=pattern.time_minute, second=0, microsecond=0)
    
    # Calculate days until the target weekday
    days_ahead = (target_weekday - target_time.weekday()) % 7
    
    # If days_ahead is 0, we're on the target day of week
    # Check if the time is still in the future
    if days_ahead == 0:
        if target_time >= candidate:
            return target_time
        # Time has passed, use next week
        days_ahead = 7
    
    return target_time + timedelta(days=days_ahead)


def _compute_monthly(
    candidate: datetime,
    pattern: RecurrencePattern,
    tz: ZoneInfo,
) -> datetime:
    """Compute next monthly execution.
    
    Matches the specified day_of_month and time_hour:time_minute.
    day_of_month: 1-31
    candidate is already adjusted to be after current time.
    """
    if pattern.day_of_month is None:
        raise ValueError("Monthly pattern requires day_of_month")
    
    candidate = candidate.replace(hour=pattern.time_hour, minute=pattern.time_minute, second=0, microsecond=0)
    
    target_day = pattern.day_of_month
    
    # Try to create the target day in the current month
    try:
        next_run = candidate.replace(day=target_day)
    except ValueError:
        # Day doesn't exist in this month (e.g., Feb 30), use last day of month
        # Move to next month and get last day
        next_month = (candidate.replace(day=1) + timedelta(days=32)).replace(day=1)
        next_run = (next_month - timedelta(days=1)).replace(hour=pattern.time_hour, minute=pattern.time_minute)
    
    # If the target date/time is in the future, use it
    if next_run > candidate:
        return next_run
    
    # Otherwise, move to next month's target day
    # Get first day of next month
    if candidate.month == 12:
        next_month_start = datetime(candidate.year + 1, 1, 1, tzinfo=tz)
    else:
        next_month_start = datetime(candidate.year, candidate.month + 1, 1, tzinfo=tz)
    
    try:
        next_run = next_month_start.replace(day=target_day, hour=pattern.time_hour, minute=pattern.time_minute)
    except ValueError:
        # Day doesn't exist in next month either, use last day of month
        next_month_end = (next_month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        next_run = next_month_end.replace(hour=pattern.time_hour, minute=pattern.time_minute)
    
    return next_run


def _compute_custom(
    candidate: datetime,
    pattern: RecurrencePattern,
    tz: ZoneInfo,
) -> datetime:
    """Compute next custom interval execution.
    
    Matches every N days/weeks/months at time_hour:time_minute.
    candidate is already adjusted to be after current time.
    """
    if pattern.custom_interval is None or pattern.custom_unit is None:
        raise ValueError("Custom pattern requires custom_interval and custom_unit")
    
    candidate = candidate.replace(hour=pattern.time_hour, minute=pattern.time_minute, second=0, microsecond=0)
    
    if pattern.custom_unit == "days":
        return candidate + timedelta(days=pattern.custom_interval)
    elif pattern.custom_unit == "weeks":
        return candidate + timedelta(weeks=pattern.custom_interval)
    elif pattern.custom_unit == "months":
        # Add months by adjusting month/year
        month_offset = pattern.custom_interval
        new_month = candidate.month + month_offset
        new_year = candidate.year
        
        # Handle year overflow
        while new_month > 12:
            new_month -= 12
            new_year += 1
        
        try:
            return candidate.replace(year=new_year, month=new_month)
        except ValueError:
            # Day doesn't exist in target month (e.g., Jan 31 + 1 month = Feb 31)
            # Use last day of target month
            if new_month == 12:
                last_day_of_month = (datetime(new_year + 1, 1, 1, tzinfo=tz) - timedelta(days=1)).day
            else:
                last_day_of_month = (datetime(new_year, new_month + 1, 1, tzinfo=tz) - timedelta(days=1)).day
            return candidate.replace(year=new_year, month=new_month, day=last_day_of_month)
    else:
        raise ValueError(f"Unknown custom unit: {pattern.custom_unit}")


def serialize_recurrence(pattern: RecurrencePattern) -> str:
    """Serialize a RecurrencePattern to an EventBridge cron/rate expression string.
    
    Returns a string suitable for use with AWS EventBridge Scheduler.
    Format: "cron(minute hour day month ? year)" for cron-based patterns
           "rate(N unit)" for simple intervals
    
    Args:
        pattern: RecurrencePattern object to serialize
        
    Returns:
        str: EventBridge Scheduler expression (cron or rate format)
    """
    if pattern.type == "daily":
        # cron(minute hour * * ? *) for every day at specified time
        return f"cron({pattern.time_minute} {pattern.time_hour} * * ? *)"
    elif pattern.type == "weekday":
        # cron(minute hour ? * MON-FRI *) for Mon-Fri at specified time
        return f"cron({pattern.time_minute} {pattern.time_hour} ? * MON-FRI *)"
    elif pattern.type == "weekly":
        # cron(minute hour ? * DAY *) for specified day at specified time
        day_names = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
        day_name = day_names[pattern.day_of_week] if pattern.day_of_week is not None else "MON"
        return f"cron({pattern.time_minute} {pattern.time_hour} ? * {day_name} *)"
    elif pattern.type == "monthly":
        # cron(minute hour day * ? *) for specified day-of-month at specified time
        day = pattern.day_of_month if pattern.day_of_month is not None else 1
        return f"cron({pattern.time_minute} {pattern.time_hour} {day} * ? *)"
    elif pattern.type == "custom":
        # Custom intervals: can't represent minutes in rate-based expressions
        # For now, we'll only support day-based custom intervals in EventBridge
        if pattern.custom_unit == "days":
            return f"rate({pattern.custom_interval} days)"
        elif pattern.custom_unit == "weeks":
            # Convert weeks to days (keeping within bounds)
            days = pattern.custom_interval * 7
            if days > 365:
                # EventBridge rate limits: max 1 year
                # For patterns > 1 year, fall back to days with a max of 365
                days = min(days, 365)
            return f"rate({days} days)"
        elif pattern.custom_unit == "months":
            # EventBridge doesn't have a "month" unit, approximate with days
            # Use 30 days per month as approximation, capped at 365
            days = min(pattern.custom_interval * 30, 365)
            return f"rate({days} days)"
    
    raise ValueError(f"Cannot serialize pattern type: {pattern.type}")


def deserialize_recurrence(cron_expr: str, timezone: str) -> RecurrencePattern:
    """Deserialize an EventBridge schedule expression to a RecurrencePattern.
    
    Args:
        cron_expr: EventBridge Scheduler expression (cron or rate format)
        timezone: IANA timezone string
        
    Returns:
        RecurrencePattern: Deserialized pattern object
        
    Raises:
        ValueError: If expression format is unrecognized
    """
    expr = cron_expr.strip()
    
    if expr.startswith("rate("):
        # Parse rate expressions: "rate(N unit)"
        parts = expr[5:-1].split()  # Remove "rate(" and ")"
        interval = int(parts[0])
        unit = parts[1].lower()
        
        if unit in ["day", "days"]:
            return RecurrencePattern(
                type="custom",
                time_hour=9,
                time_minute=0,
                timezone=timezone,
                custom_interval=interval,
                custom_unit="days",
            )
        elif unit in ["week", "weeks"]:
            return RecurrencePattern(
                type="custom",
                time_hour=9,
                time_minute=0,
                timezone=timezone,
                custom_interval=interval // 7,
                custom_unit="weeks",
            )
    elif expr.startswith("cron("):
        # Parse cron expressions: "cron(minute hour day month ? year)"
        parts = expr[5:-1].split()  # Remove "cron(" and ")"
        
        minute = int(parts[0])
        hour = int(parts[1])
        day = parts[2]
        month = parts[3]
        weekday = parts[4]
        
        if weekday != "?":
            if "MON-FRI" in weekday:
                return RecurrencePattern(
                    type="weekday",
                    time_hour=hour,
                    time_minute=minute,
                    timezone=timezone,
                )
            else:
                # Single day of week
                day_map = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}
                day_of_week = day_map.get(weekday.upper(), 0)
                return RecurrencePattern(
                    type="weekly",
                    day_of_week=day_of_week,
                    time_hour=hour,
                    time_minute=minute,
                    timezone=timezone,
                )
        elif day != "*":
            # Monthly pattern
            return RecurrencePattern(
                type="monthly",
                day_of_month=int(day),
                time_hour=hour,
                time_minute=minute,
                timezone=timezone,
            )
        else:
            # Daily pattern
            return RecurrencePattern(
                type="daily",
                time_hour=hour,
                time_minute=minute,
                timezone=timezone,
            )
    
    raise ValueError(f"Unrecognized schedule expression format: {cron_expr}")


def format_recurrence_display(pattern: RecurrencePattern) -> str:
    """Format a RecurrencePattern as a human-readable string.
    
    Converts pattern to displayable text like "Every Monday at 5:00 PM EST".
    
    Args:
        pattern: RecurrencePattern object to format
        
    Returns:
        str: Human-readable recurrence description
    """
    hour = pattern.time_hour
    minute = pattern.time_minute
    
    # Convert to 12-hour format
    am_pm = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    
    time_str = f"{display_hour}:{minute:02d} {am_pm}"
    
    # Get timezone abbreviation (simple approach, just use the timezone name)
    tz_abbr = pattern.timezone.split("/")[-1]  # e.g., "New_York" from "America/New_York"
    
    if pattern.type == "daily":
        return f"Every day at {time_str} {tz_abbr}"
    elif pattern.type == "weekday":
        return f"Every weekday (Mon-Fri) at {time_str} {tz_abbr}"
    elif pattern.type == "weekly":
        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        day_name = day_names[pattern.day_of_week] if pattern.day_of_week is not None else "Monday"
        return f"Every {day_name} at {time_str} {tz_abbr}"
    elif pattern.type == "monthly":
        day = pattern.day_of_month if pattern.day_of_month is not None else 1
        # Correct ordinal suffix logic
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix_map = {1: "st", 2: "nd", 3: "rd"}
            suffix = suffix_map.get(day % 10, "th")
        return f"Every {day}{suffix} of the month at {time_str} {tz_abbr}"
    elif pattern.type == "custom":
        interval = pattern.custom_interval if pattern.custom_interval else 1
        unit = pattern.custom_unit if pattern.custom_unit else "days"
        unit_str = unit if interval != 1 else unit.rstrip("s")
        return f"Every {interval} {unit_str} at {time_str} {tz_abbr}"
    
    return "Unknown recurrence pattern"
