import base64
from PIL import Image, ImageDraw, ImageFont
import io
import os

# Load shield icon
icon_path = '/app/static/images/ref/logo/logo-icon.png'
icon = Image.open(icon_path)

# Convert icon to base64 for embedding in SVG
buf = io.BytesIO()
icon.save(buf, format='PNG')
icon_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

# 1. White logo (for dark backgrounds)
svg_white = f'''<svg width="180" height="40" viewBox="0 0 180 40" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MARMOT">
  <image href="data:image/png;base64,{icon_b64}" x="0" y="2" width="36" height="36" preserveAspectRatio="xMidYMid meet"/>
  <text x="44" y="27" font-family="'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="21" font-weight="800" letter-spacing="1.2" fill="#f8fafc">MARMOT</text>
</svg>'''

with open('/app/static/images/ref/logo-white.svg', 'w') as f:
    f.write(svg_white)

# 2. Black/Dark logo (for light backgrounds)
svg_black = f'''<svg width="180" height="40" viewBox="0 0 180 40" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MARMOT">
  <image href="data:image/png;base64,{icon_b64}" x="0" y="2" width="36" height="36" preserveAspectRatio="xMidYMid meet"/>
  <text x="44" y="27" font-family="'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="21" font-weight="800" letter-spacing="1.2" fill="#0f172a">MARMOT</text>
</svg>'''

with open('/app/static/images/ref/logo-black.svg', 'w') as f:
    f.write(svg_black)

# 3. Favicon / App Icon SVG
svg_icon = f'''<svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MARMOT">
  <image href="data:image/png;base64,{icon_b64}" x="2" y="2" width="36" height="36" preserveAspectRatio="xMidYMid meet"/>
</svg>'''

with open('/app/static/images/ref/logo/logo-icon.svg', 'w') as f:
    f.write(svg_icon)

# 4. Copy to host static path if also running outside docker
print('SVG logos successfully generated with exact user shield image!')
