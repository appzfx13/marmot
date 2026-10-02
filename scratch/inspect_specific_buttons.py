import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

template_dir = 'templates'

# Scan ALL html files in templates/
output_rows = []
filter_rows = []

btn_tag_re = re.compile(r'<([a-zA-Z0-9]+)\b([^>]*?class=["\']([^"\']+)["\'][^>]*?)>', re.DOTALL | re.IGNORECASE)

for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            fpath = os.path.join(root, f).replace('\\', '/')
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as fp:
                lines = fp.readlines()
            
            for line_idx, line in enumerate(lines, 1):
                for m in btn_tag_re.finditer(line):
                    tag = m.group(1).lower()
                    attrs = m.group(2)
                    cls = m.group(3)
                    classes = cls.split()
                    
                    is_btn = any(c.startswith('btn-') or c == 'btn' for c in classes) or 'btn-date-picker' in classes or 'theme-pill-btn' in classes or 'btn-login' in classes or 'btn-social' in classes or 'btn-submit' in classes
                    is_pill = 'rounded-pill' in classes or 'rounded-circle' in classes
                    
                    if is_btn and not is_pill and 'btn-close' not in classes and 'btn-link' not in classes:
                        # Extract data-label or inner text or name
                        output_rows.append({
                            'file': fpath,
                            'line': line_idx,
                            'tag': tag,
                            'classes': cls,
                        })
                    
                    # Also check filter containers and search wrappers
                    if any(c in ['card-filter', 'filter-search-wrapper', 'filter-container', 'filter-bar', 'btn-group'] for c in classes):
                        if not is_pill:
                            filter_rows.append({
                                'file': fpath,
                                'line': line_idx,
                                'tag': tag,
                                'classes': cls,
                            })

print(f"Total non-pill buttons found: {len(output_rows)}")
print(f"Total non-pill filter/search/group containers found: {len(filter_rows)}")

# Group by category / folder
from collections import defaultdict
grouped_buttons = defaultdict(list)
for r in output_rows:
    # determine module
    parts = r['file'].split('/')
    module = parts[1] if len(parts) > 1 else 'root'
    grouped_buttons[module].append(r)

for mod, items in grouped_buttons.items():
    print(f"\n--- Module: {mod} ({len(items)} items) ---")
    file_sub = defaultdict(list)
    for it in items:
        file_sub[it['file']].append(it)
    for f, itms in file_sub.items():
        print(f"  {f} ({len(itms)} items):")
        for it in itms[:3]:
            print(f"    Line {it['line']} <{it['tag']}>: {it['classes']}")
        if len(itms) > 3:
            print(f"    ... and {len(itms) - 3} more")
