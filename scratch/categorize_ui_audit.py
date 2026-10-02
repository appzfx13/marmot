import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

template_dir = 'templates'
css_files = [
    'static/css/theme-shadcn.css',
    'static/css/spark-theme.css',
    'static/css/antigravity-theme.css',
    'templates/admins/index.html',
    'templates/users/index.html'
]

categories = {
    'Header & Topbar Controls': [],
    'Filter Bars & Search Wrappers': [],
    'Segmented Controls & Button Groups': [],
    'Table Actions & Pagination': [],
    'Terminal & Gateway Trading Controls': [],
    'Chart HUD & Toolbars': [],
    'Modal Action Buttons': [],
    'Auth & Account Forms': [],
    'Global CSS Design System Tokens': []
}

# 1. Audit CSS Tokens
with open('static/css/theme-shadcn.css', 'r', encoding='utf-8') as f:
    shadcn = f.read()

for line_idx, line in enumerate(shadcn.splitlines(), 1):
    if any(k in line for k in ['.btn {', '.btn-date-picker', '.btn-group', '.btn-primary', '.btn-outline-primary', '--radius:']):
        categories['Global CSS Design System Tokens'].append({
            'file': 'static/css/theme-shadcn.css',
            'line': line_idx,
            'code': line.strip(),
            'issue': 'Hardcodes border-radius to 8px/10px (calc(var(--radius) - 2px)) overriding 50px pill shape'
        })

# 2. Audit Templates
tag_re = re.compile(r'<([a-zA-Z0-9]+)\b([^>]*?class=["\']([^"\']+)["\'][^>]*?)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)

for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            p = os.path.join(root, f).replace('\\', '/')
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
            
            for m in tag_re.finditer(content):
                tag = m.group(1).lower()
                attrs = m.group(2)
                cls = m.group(3)
                inner = re.sub(r'<[^>]+>', '', m.group(4)).strip()
                inner = ' '.join(inner.split())[:35]
                classes = set(cls.split())
                
                is_pill = 'rounded-pill' in classes or 'rounded-circle' in classes
                is_close = 'btn-close' in classes
                is_link = 'btn-link' in classes
                
                line_no = content[:m.start()].count('\n') + 1
                
                # Check btn-date-picker
                if 'btn-date-picker' in classes:
                    if 'pagination' in p or 'table' in p:
                        categories['Table Actions & Pagination'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Square/Boxy (8px radius via CSS)', 'target': 'Rounded Pill (rounded-pill)'
                        })
                    else:
                        categories['Header & Topbar Controls'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Square/Boxy (8px radius via CSS)', 'target': 'Curved Pill (rounded-pill)'
                        })
                
                # Check btn-group
                elif 'btn-group' in classes:
                    if not is_pill:
                        categories['Segmented Controls & Button Groups'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Square / rounded-3 (6-8px radius)', 'target': 'Rounded Pill Container (rounded-pill)'
                        })
                
                # Check regular buttons without pill
                elif any(c.startswith('btn-') or c == 'btn' for c in classes) and not is_pill and not is_close and not is_link:
                    if 'modal' in p or 'confirm' in p:
                        categories['Modal Action Buttons'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Default square button (6-8px)', 'target': 'Curved Pill (rounded-pill)'
                        })
                    elif 'chart' in p:
                        categories['Chart HUD & Toolbars'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Square tabs / timeframe buttons', 'target': 'Curved Pill buttons'
                        })
                    elif 'terminal' in p or 'gateway' in p:
                        categories['Terminal & Gateway Trading Controls'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'rounded-3 / square buttons', 'target': 'Curved Pill (rounded-pill)'
                        })
                    elif 'registration' in p or 'login' in p or 'password' in p:
                        categories['Auth & Account Forms'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Slightly rounded rectangular inputs/buttons', 'target': 'Curved Pill (rounded-pill)'
                        })
                    else:
                        categories['Header & Topbar Controls'].append({
                            'file': p, 'line': line_no, 'element': f'<{tag}> {inner}', 'class': cls,
                            'current': 'Square/Boxy (8px radius)', 'target': 'Curved Pill (rounded-pill)'
                        })

print("=== AUDIT RESULTS BY CATEGORY ===")
for cat, items in categories.items():
    print(f"\n### {cat} ({len(items)} items)")
    for it in items[:6]:
        if 'element' in it:
            print(f"  - [{it['file']}:{it['line']}] {it['element']} | Current: {it['current']} -> Target: {it['target']}")
        else:
            print(f"  - [{it['file']}:{it['line']}] {it['code']} -> {it['issue']}")
    if len(items) > 6:
        print(f"  ... and {len(items) - 6} more")
