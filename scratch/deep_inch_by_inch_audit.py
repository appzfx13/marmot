import os
import re
import sys
from html.parser import HTMLParser
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

template_dir = 'templates'

class TemplateParser(HTMLParser):
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self.findings = []
        self.current_tag = None
        self.current_attrs = {}
        self.current_text = []
        self.recording = False

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls_str = attr_dict.get('class', '')
        classes = cls_str.split()
        
        is_btn = any(c.startswith('btn-') or c == 'btn' for c in classes) or 'btn-date-picker' in classes or 'theme-pill-btn' in classes or 'btn-login' in classes or 'btn-social' in classes or 'btn-submit' in classes
        is_filter = any(c in ['card-filter', 'filter-search-wrapper', 'filter-bar', 'filter-widget', 'btn-group'] for c in classes)
        
        if is_btn or is_filter:
            is_pill = 'rounded-pill' in classes or 'rounded-circle' in classes
            is_close = 'btn-close' in classes
            is_link = 'btn-link' in classes
            
            if not (is_close or is_link):
                # Categorize
                category = 'General Buttons & Actions'
                if 'btn-date-picker' in classes:
                    category = 'Action Link / Date Picker Buttons'
                elif 'btn-group' in classes:
                    category = 'Segmented Button Groups'
                elif any(c in ['card-filter', 'filter-search-wrapper', 'filter-bar'] for c in classes):
                    category = 'Filter Sections & Search Wrappers'
                elif any(k in self.filepath for k in ['login', 'signup', 'password']):
                    category = 'Auth & Form Action Buttons'
                elif 'chart' in self.filepath:
                    category = 'Chart Toolbar & Timeframe Controls'
                elif 'modal' in self.filepath:
                    category = 'Modal & Dialog Confirmation Actions'
                elif any(k in self.filepath for k in ['terminal', 'emulator', 'gateway']):
                    category = 'Trading Cockpit & Terminal Controls'
                elif any(k in self.filepath for k in ['header', 'nav', 'dashboard']):
                    category = 'Header, Navbar & Topbar Controls'
                
                self.findings.append({
                    'file': self.filepath,
                    'line': self.getpos()[0],
                    'tag': tag,
                    'classes': cls_str,
                    'is_pill': is_pill,
                    'is_filter': is_filter,
                    'is_btn': is_btn,
                    'category': category
                })

all_findings = []
for root, dirs, files in os.walk(template_dir):
    for f in files:
        if f.endswith('.html'):
            filepath = os.path.join(root, f).replace('\\', '/')
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
            parser = TemplateParser(filepath)
            try:
                parser.feed(content)
                all_findings.extend(parser.findings)
            except Exception as e:
                pass

print(f"Total interactive elements inspected across all templates: {len(all_findings)}")
square_findings = [f for f in all_findings if not f['is_pill']]
pill_findings = [f for f in all_findings if f['is_pill']]

print(f"  - Curved / Rounded Pill: {len(pill_findings)}")
print(f"  - Square / Slightly Boxy: {len(square_findings)}")

# Group square findings by category
by_cat = defaultdict(list)
for item in square_findings:
    by_cat[item['category']].append(item)

for cat, items in by_cat.items():
    print(f"\n=======================================================")
    print(f"CATEGORY: {cat} ({len(items)} items)")
    print(f"=======================================================")
    seen = set()
    for it in items:
        key = (it['file'], it['classes'])
        if key not in seen:
            seen.add(key)
            print(f"  [{it['file']}:{it['line']}] <{it['tag']}> class='{it['classes']}'")
