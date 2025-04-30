def format_currency(value):
    """Format a number as currency in VND"""
    if value is None:
        return "N/A"
    try:
        # Convert to float if it's a string
        value = float(value)
        # Format with commas and VND symbol
        return f"{value:,.0f} ₫"
    except (ValueError, TypeError):
        return "N/A" 