from datetime import datetime

def format_datetime_filter(dt):
    """Format datetime to show only date"""
    if dt is None:
        return "N/A"
    try:
        if isinstance(dt, str):
            # If it's a string, try to parse it
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        elif isinstance(dt, (int, float)):
            # If it's a timestamp
            dt = datetime.fromtimestamp(dt)
        
        # Format as date only (YYYY-MM-DD)
        return dt.strftime('%Y/%m/%d')
    except (ValueError, TypeError):
        return "N/A"

def timestamp_to_date(timestamp):
    """Convert timestamp to date string"""
    if timestamp is None:
        return "N/A"
    try:
        # Convert timestamp to datetime
        dt = datetime.fromtimestamp(timestamp)
        # Format as date only (YYYY-MM-DD)
        return dt.strftime('%Y/%m/%d')
    except (ValueError, TypeError):
        return "N/A"
