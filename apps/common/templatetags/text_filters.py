from django import template

register = template.Library()


@register.filter
def custom_filter(value):
    return value


@register.filter
def format_precise_time(value):
    """Formats a UTC timestamp, datetime object, or date string into human-readable IST (UTC+05:30)."""
    if not value or str(value).strip() in ('', '-', 'None', '0001-01-01T00:00:00Z'):
        return '-'
    from datetime import datetime, date
    from django.utils import timezone
    ist = timezone.get_fixed_timezone(330)

    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    val_str = str(value).strip()
    if len(val_str) <= 12 and ':' in val_str and '-' not in val_str:
        try:
            parts = val_str.split(':')
            h, m = int(parts[0]), int(parts[1])
            s = float(parts[2]) if len(parts) > 2 else 0.0
            today = timezone.localdate()
            dt_utc = datetime(today.year, today.month, today.day, h, m, int(s), tzinfo=timezone.utc)
            return dt_utc.astimezone(ist).strftime("%H:%M:%S")
        except Exception:
            return val_str

    try:
        clean_str = val_str.replace('Z', '+00:00')
        if 'T' not in clean_str and ' ' in clean_str:
            clean_str = clean_str.replace(' ', 'T')
        has_offset = ('+' in clean_str[10:]) or ('-' in clean_str[10:])
        if not has_offset:
            clean_str = f"{clean_str}+00:00"
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ist).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return val_str