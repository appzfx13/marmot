from django import template

register = template.Library()


@register.filter
def custom_filter(value):
    return value


@register.filter
def format_precise_time(value):
    """Formats an ISO timestamp or date object into human-readable HH:MM:SS.mmm AM/PM (IST)."""
    if not value or str(value).strip() in ('', '-', 'None', '0001-01-01T00:00:00Z'):
        return '-'
    val_str = str(value).strip()
    if 'T' not in val_str and not val_str.endswith('Z'):
        return val_str
    try:
        clean_str = val_str.rstrip('Z')
        if '.' in clean_str:
            base, frac = clean_str.split('.', 1)
            frac = (frac + '000000')[:6]
            clean_str = f"{base}.{frac}+00:00"
        else:
            clean_str = f"{clean_str}+00:00"
        from datetime import datetime
        from django.utils import timezone
        dt = datetime.fromisoformat(clean_str)
        ist = timezone.get_fixed_timezone(330)
        dt_ist = dt.astimezone(ist)
        millis = dt_ist.microsecond // 1000
        return dt_ist.strftime(f"%I:%M:%S.{millis:03d} %p")
    except Exception:
        return val_str