import datetime

def format_datetime_filter(value, format='%b %d, %Y %H:%M'):
    """Formats an ISO datetime string into a more readable format."""
    if not value:
        return ""
    try:
        # Attempt to parse the ISO format string
        dt_object = datetime.datetime.fromisoformat(value)
        return dt_object.strftime(format)
    except (ValueError, TypeError):
        # Handle cases where the value is not a valid ISO string or None
        # You might want to log this error or return a default value
        return str(value) # Return original value or some placeholder
