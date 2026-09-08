#!/usr/bin/env python
"""Fix Unicode characters in pipeline script."""

import sys

filepath = "backend/app/process_pipeline.py"
content = open(filepath, encoding="utf-8").read()

# Replace Unicode with ASCII
replacements = {
    "✓": "[OK]",
    "✗": "[FAIL]",
    "→": "->",
    "↓": "|",
}

for unicode_char, ascii_char in replacements.items():
    content = content.replace(unicode_char, ascii_char)

open(filepath, "w", encoding="utf-8").write(content)
print("Fixed Unicode characters")
