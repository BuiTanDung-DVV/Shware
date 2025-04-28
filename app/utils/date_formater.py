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

def timestamp_to_date(timestamp):
    """Convert millisecond timestamp to formatted date string"""
    if not timestamp:
        return 'N/A'
    try:
        # Convert milliseconds to seconds if needed
        if isinstance(timestamp, int) and len(str(timestamp)) > 10:
            timestamp = timestamp / 1000
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime('%d/%m/%Y %H:%M')
    except:
        return 'N/A'
