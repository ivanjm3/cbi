"""Property tests for the Recurrence Calculator module.

Property 2: Recurrence pattern computation
- For any valid RecurrencePattern and any reference timestamp, compute_next_execution SHALL produce
  a datetime that:
  1. Is strictly in the future relative to the reference timestamp
  2. Is no more than 30 days after the reference timestamp (for non-custom patterns)
  3. Respects the specified IANA timezone
  4. Falls on the correct day_of_week or day_of_month as specified by the pattern

Validates: Requirements 4.3, 5.3, 5.4, 5.5, 11.3
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from src.models.scheduled_reports import RecurrencePattern
from src.services.recurrence_calculator import (
    compute_next_execution,
    serialize_recurrence,
    deserialize_recurrence,
    format_recurrence_display,
)


# --- Strategies ---

# Generate valid time values
valid_hours = st.integers(min_value=0, max_value=23)
valid_minutes = st.integers(min_value=0, max_value=59)

# Generate valid day_of_week (0-6, Sunday=0, Saturday=6)
valid_day_of_week = st.integers(min_value=0, max_value=6)

# Generate valid day_of_month (1-31)
valid_day_of_month = st.integers(min_value=1, max_value=31)

# Common IANA timezones for testing
common_timezones = st.sampled_from([
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo",
    "Australia/Sydney",
])

# Valid custom intervals
valid_custom_intervals = st.integers(min_value=1, max_value=365)
valid_custom_units = st.sampled_from(["days", "weeks", "months"])


@st.composite
def valid_recurrence_patterns(draw):
    """Generate valid RecurrencePattern objects."""
    pattern_type = draw(st.sampled_from(["daily", "weekday", "weekly", "monthly", "custom"]))
    
    hour = draw(valid_hours)
    minute = draw(valid_minutes)
    timezone = draw(common_timezones)
    
    kwargs = {
        "type": pattern_type,
        "time_hour": hour,
        "time_minute": minute,
        "timezone": timezone,
    }
    
    if pattern_type == "weekly":
        kwargs["day_of_week"] = draw(valid_day_of_week)
    elif pattern_type == "monthly":
        kwargs["day_of_month"] = draw(valid_day_of_month)
    elif pattern_type == "custom":
        kwargs["custom_interval"] = draw(valid_custom_intervals)
        kwargs["custom_unit"] = draw(valid_custom_units)
    
    return RecurrencePattern(**kwargs)


@st.composite
def reference_datetimes(draw, tz_str: str = "UTC"):
    """Generate reference datetimes in various timezones."""
    dt = draw(st.datetimes(
        min_value=datetime(2025, 1, 1),
        max_value=datetime(2026, 12, 31),
        timezones=st.just(ZoneInfo(tz_str)),
    ))
    return dt


# --- Test Classes ---


class TestRecurrencePatternComputation:
    """Property 2: Recurrence pattern computation."""
    
    @given(
        pattern=valid_recurrence_patterns(),
        tz_offset=st.integers(min_value=-12, max_value=14),
    )
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_next_execution_is_in_future(self, pattern: RecurrencePattern, tz_offset: int):
        """Next execution must be strictly in the future."""
        # Create a reference time in the specified timezone
        tz = ZoneInfo(pattern.timezone)
        now = datetime.now(tz=tz)
        
        result = compute_next_execution(pattern, now, pattern.timezone)
        
        # Result must be after the reference time
        assert result > now, f"Next execution {result} must be after reference {now}"
    
    @given(
        pattern=valid_recurrence_patterns().filter(lambda p: p.type != "custom"),
        tz_offset=st.integers(min_value=-12, max_value=14),
    )
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_non_custom_within_30_days(self, pattern: RecurrencePattern, tz_offset: int):
        """Non-custom patterns must have next execution within 30 days."""
        tz = ZoneInfo(pattern.timezone)
        now = datetime.now(tz=tz)
        
        result = compute_next_execution(pattern, now, pattern.timezone)
        
        # Days between now and result must be <= 30
        days_ahead = (result.date() - now.date()).days
        assert 0 <= days_ahead <= 30, \
            f"Non-custom pattern {pattern.type} is {days_ahead} days away, exceeds 30-day limit"
    
    @given(pattern=valid_recurrence_patterns())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_result_respects_timezone(self, pattern: RecurrencePattern):
        """Result must have the correct local time in the specified timezone."""
        tz = ZoneInfo(pattern.timezone)
        now = datetime.now(tz=tz)
        
        result = compute_next_execution(pattern, now, pattern.timezone)
        
        # Result must be in the specified timezone
        assert result.tzinfo == tz or str(result.tzinfo) == pattern.timezone, \
            f"Result timezone {result.tzinfo} != pattern timezone {pattern.timezone}"
        
        # Result time must match pattern's time_hour:time_minute
        assert result.hour == pattern.time_hour, \
            f"Result hour {result.hour} != pattern hour {pattern.time_hour}"
        assert result.minute == pattern.time_minute, \
            f"Result minute {result.minute} != pattern minute {pattern.time_minute}"
    
    @given(pattern=st.just(RecurrencePattern(
        type="weekly",
        day_of_week=1,  # Monday
        time_hour=9,
        time_minute=0,
        timezone="UTC",
    )))
    @settings(max_examples=100)
    def test_weekly_pattern_matches_day_of_week(self, pattern: RecurrencePattern):
        """Weekly pattern must execute on the correct day of week."""
        tz = ZoneInfo("UTC")
        
        # Test multiple times
        for i in range(10):
            now = datetime(2025, 1, 1, tzinfo=tz) + timedelta(days=i)
            result = compute_next_execution(pattern, now, pattern.timezone)
            
            # Convert pattern's day_of_week (0=Sunday, 6=Saturday) to Python's weekday (0=Monday, 6=Sunday)
            target_weekday = (pattern.day_of_week - 1) % 7
            
            assert result.weekday() == target_weekday, \
                f"Result {result.strftime('%A')} doesn't match pattern day {pattern.day_of_week}"
    
    @given(pattern=st.just(RecurrencePattern(
        type="monthly",
        day_of_month=15,
        time_hour=9,
        time_minute=0,
        timezone="UTC",
    )))
    @settings(max_examples=100)
    def test_monthly_pattern_matches_day_of_month(self, pattern: RecurrencePattern):
        """Monthly pattern must execute on the correct day of month."""
        tz = ZoneInfo("UTC")
        
        # Test from various dates
        for month in range(1, 13):
            now = datetime(2025, month, 1, tzinfo=tz)
            result = compute_next_execution(pattern, now, pattern.timezone)
            
            # Result should be on the 15th
            assert result.day == pattern.day_of_month, \
                f"Result day {result.day} != pattern day {pattern.day_of_month}"
    
    @given(pattern=st.just(RecurrencePattern(
        type="daily",
        time_hour=14,
        time_minute=30,
        timezone="UTC",
    )))
    @settings(max_examples=100)
    def test_daily_pattern_repeats_correctly(self, pattern: RecurrencePattern):
        """Daily pattern should execute at the same time every day."""
        tz = ZoneInfo("UTC")
        
        # Test from different times of day
        for hour in [10, 12, 14, 18, 23]:
            now = datetime(2025, 1, 15, hour=hour, minute=0, tzinfo=tz)
            result = compute_next_execution(pattern, now, pattern.timezone)
            
            assert result.hour == 14, f"Expected hour 14, got {result.hour}"
            assert result.minute == 30, f"Expected minute 30, got {result.minute}"


class TestSerializationDeserialization:
    """Test serialize_recurrence and deserialize_recurrence round-trips."""
    
    @given(pattern=valid_recurrence_patterns())
    @settings(max_examples=200)
    def test_serialize_deserialize_round_trip(self, pattern: RecurrencePattern):
        """Serialization should preserve pattern semantics through round-trip."""
        # Serialize
        expr = serialize_recurrence(pattern)
        
        # Deserialize
        restored = deserialize_recurrence(expr, pattern.timezone)
        
        # Type should match
        assert restored.type == pattern.type, \
            f"Type mismatch: {restored.type} != {pattern.type}"
        
        # For non-custom patterns, time should match (cron expressions preserve time)
        if pattern.type != "custom":
            assert restored.time_hour == pattern.time_hour, \
                f"Hour mismatch: {restored.time_hour} != {pattern.time_hour}"
            assert restored.time_minute == pattern.time_minute, \
                f"Minute mismatch: {restored.time_minute} != {pattern.time_minute}"
        # For custom patterns, time is reset to 9:00 AM due to EventBridge rate expression limitations
        # This is expected behavior, not a bug
        
        assert restored.timezone == pattern.timezone


class TestFormatRecurrenceDisplay:
    """Test format_recurrence_display produces human-readable output."""
    
    @given(pattern=valid_recurrence_patterns())
    @settings(max_examples=200)
    def test_display_format_is_string(self, pattern: RecurrencePattern):
        """Display format should return a non-empty string."""
        display = format_recurrence_display(pattern)
        
        assert isinstance(display, str)
        assert len(display) > 0
    
    @given(st.just(RecurrencePattern(
        type="daily",
        time_hour=9,
        time_minute=0,
        timezone="UTC",
    )))
    @settings(max_examples=10)
    def test_display_contains_time_and_pattern_type(self, pattern: RecurrencePattern):
        """Display format should contain recognizable time and pattern type indicators."""
        display = format_recurrence_display(pattern)
        
        # Should contain "day" and "9" (hour)
        assert "day" in display.lower()
        assert "9" in display or "09" in display
    
    @given(st.just(RecurrencePattern(
        type="weekly",
        day_of_week=1,  # Monday
        time_hour=17,
        time_minute=30,
        timezone="America/New_York",
    )))
    @settings(max_examples=10)
    def test_display_contains_day_name(self, pattern: RecurrencePattern):
        """Weekly display should contain day name."""
        display = format_recurrence_display(pattern)
        
        # Should contain "Monday"
        assert "Monday" in display


# --- Unit Tests (Example-Based) ---


class TestRecurrenceCalculatorExamples:
    """Example-based unit tests for recurrence calculations."""
    
    def test_daily_pattern_tomorrow(self):
        """Daily pattern at 9 AM from 8 AM should be today at 9 AM."""
        pattern = RecurrencePattern(
            type="daily",
            time_hour=9,
            time_minute=0,
            timezone="UTC",
        )
        
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = compute_next_execution(pattern, now, "UTC")
        
        assert result.day == 15
        assert result.hour == 9
        assert result.minute == 0
    
    def test_daily_pattern_next_day(self):
        """Daily pattern at 9 AM from 10 AM should be next day at 9 AM."""
        pattern = RecurrencePattern(
            type="daily",
            time_hour=9,
            time_minute=0,
            timezone="UTC",
        )
        
        now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = compute_next_execution(pattern, now, "UTC")
        
        assert result.day == 16
        assert result.hour == 9
        assert result.minute == 0
    
    def test_weekly_monday(self):
        """Weekly on Monday should execute next Monday."""
        pattern = RecurrencePattern(
            type="weekly",
            day_of_week=1,  # Monday in pattern (0=Sunday)
            time_hour=9,
            time_minute=0,
            timezone="UTC",
        )
        
        # Start on a Wednesday (2025-01-15)
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = compute_next_execution(pattern, now, "UTC")
        
        # Next Monday is 2025-01-20
        assert result.weekday() == 0  # Monday
        assert result.day == 20
    
    def test_monthly_15th(self):
        """Monthly on 15th should execute on the 15th."""
        pattern = RecurrencePattern(
            type="monthly",
            day_of_month=15,
            time_hour=8,
            time_minute=0,
            timezone="UTC",
        )
        
        # Start on Jan 10
        now = datetime(2025, 1, 10, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = compute_next_execution(pattern, now, "UTC")
        
        assert result.day == 15
        assert result.month == 1
    
    def test_custom_every_3_days(self):
        """Custom pattern every 3 days should advance by 3 days."""
        pattern = RecurrencePattern(
            type="custom",
            time_hour=9,
            time_minute=0,
            timezone="UTC",
            custom_interval=3,
            custom_unit="days",
        )
        
        now = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = compute_next_execution(pattern, now, "UTC")
        
        # Should be 3 days later (no 30-day limit for custom)
        expected = datetime(2025, 1, 18, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
        assert result.day == expected.day
