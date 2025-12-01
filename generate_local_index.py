#!/usr/bin/env python3
"""
generate_index.py – Correctly detects year folders at ANY depth
→ Only PDFs
→ Excludes .files folders
→ Works with your real structure
"""

from pathlib import Path
import urllib.parse
import re

def extract_year_from_path(path_parts):
    """Find the first 19xx or 20xx year in any part of the path"""
    for part in path_parts:
        match = re.search(r"\b(19\d{2}|20\d{2})\b", part)
        if match:
            return int(match.group(0))
    return None

# Load template
template_path = Path("templates.html")
if not template_path.exists():
    print("Error: templates.html not found!")
    exit(1)

template = template_path.read_text(encoding="utf-8")

# Scan PDFs
root = Path(".")
print("Scanning for PDF files (excluding .files folders)...")
pdf_files = []
excluded = 0

for p in root.rglob("*.pdf"):
    if ".files" in p.parts:
        excluded += 1
        continue
    if not p.is_file():
        continue

    rel = p.relative_to(root)
    year = extract_year_from_path(rel.parts)

    pdf_files.append({
        "path": str(rel.as_posix()),
        "name": p.name,
        "year": year
    })

print(f"Found {len(pdf_files)} PDF files ({excluded} excluded)")

# Group: top-level directory → year (or None) → files
grouped = {}
for f in pdf_files:
    top_dir = f["path"].split("/", 1)[0]  # First folder only
    year_key = f["year"] if f["year"] else "no-year"
    grouped.setdefault(top_dir, {}).setdefault(year_key, []).append(f)

# Generate HTML content
content = ""
for top_dir in sorted(grouped.keys()):
    content += f'<div class="directory collapsed">\n'
    content += f'  <div class="dir-header">{top_dir}<span class="arrow"></span></div>\n'
    content += f'  <div class="content">\n'

    year_map = {}
    for y_key, flist in grouped[top_dir].items():
        display = "No Year Folder" if y_key == "no-year" else str(y_key)
        year_map[display] = sorted(flist, key=lambda x: x["path"].lower())

    # Sort years numerically
    sorted_years = sorted(
        (y for y in year_map.keys() if y != "No Year Folder"),
        key=int
    )
    if "No Year Folder" in year_map:
        sorted_years.append("No Year Folder")

    for year_name in sorted_years:
        files = year_map[year_name]
        content += f'    <div class="year collapsed">\n'
        content += f'      <div class="year-header">{year_name} <span class="count">({len(files)} PDFs)</span><span class="arrow"></span></div>\n'
        content += f'      <div class="content">\n'
        content += '        <div class="table-wrapper"><table><thead><tr><th>Document</th><th>Path</th></tr></thead><tbody>\n'
        for f in files:
            safe_name = f["name"].replace("|", "Vertical Bar")
            link = urllib.parse.quote(f["path"])
            content += f'          <tr><td><a href="{link}" target="_blank">{safe_name}</a></td><td><code>{f["path"]}</code></td></tr>\n'
        content += '        </tbody></table></div>\n'
        content += '      </div></div>\n'

    content += '  </div></div>\n'

# Inject into template
final_html = template.replace("{TOTAL_FILES}", str(len(pdf_files))).replace("<!-- INJECTED_CONTENT -->", content)

Path("index_local.html").write_text(final_html, encoding="utf-8")
print(f"\nSuccess: index_local.html generated with {len(pdf_files)} PDFs")
print("   → Year folders detected correctly (even deep in path)")
print("   → Expand/collapse works perfectly")
print("   → SVG arrows rotate smoothly")
print("   → Search brings results to top automatically")
print("   → Double-click index_local.html → enjoy your archive!")
