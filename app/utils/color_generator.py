def generate_colors(n):
    """Generate n distinct colors using HSV color space for better distinction"""
    colors = []
    for i in range(n):
        # Use golden ratio to get well-distributed hues
        hue = i * 0.618033988749895 % 1
        # Convert HSV to RGB (using lower saturation and higher value for pastel colors)
        h = hue * 6
        c = 0.6  # Giảm saturation xuống từ 0.8 thành 0.6
        x = c * (1 - abs(h % 2 - 1))
        
        if h < 1:
            rgb = (c, x, 0)
        elif h < 2:
            rgb = (x, c, 0)
        elif h < 3:
            rgb = (0, c, x)
        elif h < 4:
            rgb = (0, x, c)
        elif h < 5:
            rgb = (x, 0, c)
        else:
            rgb = (c, 0, x)
            
        # Convert to 0-255 range and then to hex
        # Tăng lightness bằng cách thêm 0.4 thay vì 0.2
        r = int((rgb[0] + 0.4) * 255)
        g = int((rgb[1] + 0.4) * 255)
        b = int((rgb[2] + 0.4) * 255)
        
        # Đảm bảo giá trị không vượt quá 255
        r = min(r, 255)
        g = min(g, 255)
        b = min(b, 255)
        
        colors.append(f'#{r:02x}{g:02x}{b:02x}')
    
    return colors