import os
import re
from collections import defaultdict

template_dir = 'templates'

# Tag regex to catch buttons, button-links, inputs with btn class, etc.
tag_re = re.compile(r'<([a-zA-Z0-9]+)\b([^>]*?)>', re.DOTALL)
class_re = re.compile(r'class=["\']([^"\']+)["\']')

results = {
    'buttons_square': [],
    'buttons_pill': [],
    'date_pickers': [],
    'filter_bars_and_search': [],
    'btn_groups': [],
    'modal_actions': [],
    'chart_controls': [],
}

file_summary = defaultdict(lambda: {'square': 0, 'pill': 0, 'details': []})

for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f).replace('\\', '/')
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                
            # Scan all HTML tags
            for match in tag_re.finditer(content):
                tag_name = match.group(1).lower()
                attrs = match.group(2)
                cls_match = class_re.search(attrs)
                if not cls_match:
                    continue
                
                cls_str = cls_match.group(1)
                classes = cls_str.split()
                
                is_btn = any(c.startswith('btn-') or c == 'btn' for c in classes) or 'btn-date-picker' in classes or 'theme-pill-btn' in classes
                is_pill = 'rounded-pill' in classes or 'rounded-circle' in classes
                
                # Line number
                line_no = content[:match.start()].count('\n') + 1
                
                # Check btn-date-picker
                if 'btn-date-picker' in classes:
                    results['date_pickers'].append({
                        'file': path, 'line': line_no, 'tag': tag_name, 'class': cls_str, 'is_pill': is_pill
                    })
                
                # Check filter container or search wrapper
                if any(c in ['card-filter', 'filter-search-wrapper', 'filter-bar', 'filter-container'] for c in classes):
                    results['filter_bars_and_search'].append({
                        'file': path, 'line': line_no, 'tag': tag_name, 'class': cls_str, 'is_pill': is_pill
                    })
                
                # Check btn-group
                if 'btn-group' in classes:
                    results['btn_groups'].append({
                        'file': path, 'line': line_no, 'tag': tag_name, 'class': cls_str, 'is_pill': is_pill
                    })
                
                # If it's a button or button link
                if is_btn:
                    if is_pill:
                        results['buttons_pill'].append({
                            'file': path, 'line': line_no, 'tag': tag_name, 'class': cls_str
                        })
                        file_summary[path]['pill'] += 1
                    else:
                        results['buttons_square'].append({
                            'file': path, 'line': line_no, 'tag': tag_name, 'class': cls_str
                        })
                        file_summary[path]['square'] += 1
                        file_summary[path]['details'].append((line_no, tag_name, cls_str))

print("=== AUDIT SUMMARY ===")
print(f"Total Square / Inconsistent Buttons: {len(results['buttons_square'])}")
print(f"Total Rounded Pill Buttons: {len(results['buttons_pill'])}")
print(f"Total Date Pickers: {len(results['date_pickers'])}")
print(f"Total Filter Bars & Search Wrappers: {len(results['filter_bars_and_search'])}")
print(f"Total Button Groups (Segmented Controls): {len(results['btn_groups'])}")

print("\n=== FILES WITH SQUARE BUTTONS ===")
for p, data in sorted(file_summary.items(), key=lambda x: x[1]['square'], reverse=True):
    if data['square'] > 0:
        print(f"\n{p} ({data['square']} square, {data['pill']} pill):")
        for line_no, tag, cls in data['details'][:5]:
            print(f"   Line {line_no} <{tag}>: {cls}")
        if len(data['details']) > 5:
            print(f"   ... and {len(data['details']) - 5} more")
