import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

template_dir = 'templates'

filter_classes = ['card-filter', 'filter-search-wrapper', 'filter-bar', 'filter-container', 'filter-wrapper', 'btn-group']

matches = []

for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            p = os.path.join(root, f).replace('\\', '/')
            with open(p, 'r', encoding='utf-8', errors='ignore') as fp:
                lines = fp.readlines()
            for idx, line in enumerate(lines, 1):
                for fc in filter_classes:
                    if fc in line:
                        matches.append((p, idx, fc, line.strip()[:110]))

print(f"Total occurrences of filter classes: {len(matches)}")
for m in matches:
    print(f"{m[0]}:{m[1]} [{m[2]}] -> {m[3]}")
