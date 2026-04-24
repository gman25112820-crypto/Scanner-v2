"""
RAGE Engine — fix_unicode.py
=============================
Double-click this once. It fixes every .py file in scanner_v2 so
Windows cp1252 terminals never crash on unicode characters again.

What it does:
  1. Replaces problem unicode chars in print/log statements
     → becomes ->
     ✅ becomes [OK]
     ❌ becomes [ERROR]
     ⚠  becomes [WARN]
     │  becomes |
  2. Adds UTF-8 stdout fix to any __main__ block that uses print()
  3. Never touches app.py (Streamlit handles its own encoding fine)
  4. Creates a .bak backup of every file it changes
"""

import os
import re
import sys
import shutil
from pathlib import Path

# ── Config ────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
SKIP_FILES = {"app.py", "fix_unicode.py"}  # leave these alone

# Simple character replacements (in print/log strings)
REPLACEMENTS = [
    ("→",  "->"),
    ("✅",  "[OK]"),
    ("❌",  "[ERROR]"),
    ("⚠️",  "[WARN]"),
    ("⚠",   "[WARN]"),
    ("│",   "|"),
    ("•",   "-"),
    ("🐉",  ""),
    ("🏴",  ""),
    ("\u2192", "->"),
    ("\u2705", "[OK]"),
    ("\u274c", "[ERROR]"),
    ("\u26a0", "[WARN]"),
    ("\u2502", "|"),
]

# UTF-8 fix to inject at start of main() blocks
UTF8_FIX = """\
    # -- Windows UTF-8 fix (auto-added by fix_unicode.py) --
    import io as _io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""

# ── Helpers ───────────────────────────────────────────────────

def needs_utf8_fix(content: str) -> bool:
    """True if file has a __main__ block with print() but no UTF-8 fix yet."""
    return (
        'if __name__ == "__main__"' in content
        and "print(" in content
        and "UTF-8 fix" not in content
        and "TextIOWrapper" not in content
    )


def inject_utf8_fix(content: str) -> str:
    """Inject the UTF-8 fix as the first lines inside the __main__ block."""
    # Match:  if __name__ == "__main__":\n    (first line of block)
    pattern = r'(if __name__ == ["\']__main__["\']:\n)([ \t]+)'
    match = re.search(pattern, content)
    if not match:
        return content

    insert_pos = match.end(0) - len(match.group(2))  # start of first indented line
    # Build the fix using the same indentation as the block
    indent = match.group(2)
    fix_lines = "\n".join(
        indent + line.lstrip() if line.strip() else ""
        for line in UTF8_FIX.strip().splitlines()
    ) + "\n"

    return content[:insert_pos] + fix_lines + "\n" + content[insert_pos:]


def fix_file(path: Path) -> tuple[bool, str]:
    """
    Fix a single .py file.
    Returns (changed: bool, reason: str)
    """
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"read error: {e}"

    content = original

    # Step 1 — character replacements
    for bad, good in REPLACEMENTS:
        content = content.replace(bad, good)

    # Step 2 — UTF-8 stdout injection
    if needs_utf8_fix(content):
        content = inject_utf8_fix(content)

    if content == original:
        return False, "no changes needed"

    # Backup
    shutil.copy2(path, path.with_suffix(".py.bak"))

    try:
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        # Restore backup
        shutil.copy2(path.with_suffix(".py.bak"), path)
        return False, f"write error: {e}"

    return True, "fixed"


# ── Main ──────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  RAGE Engine -- Unicode Fixer")
    print("=" * 52)
    print(f"\n  Scanning: {BASE_DIR}\n")

    py_files = sorted(BASE_DIR.glob("*.py"))
    py_files = [f for f in py_files if f.name not in SKIP_FILES]

    if not py_files:
        print("  No .py files found.")
        input("\n  Press Enter to close...")
        return

    changed = []
    skipped = []

    for f in py_files:
        ok, reason = fix_file(f)
        if ok:
            changed.append(f.name)
            print(f"  [FIXED]   {f.name}")
        else:
            skipped.append(f.name)
            print(f"  [OK]      {f.name}  ({reason})")

    print("\n" + "=" * 52)
    print(f"  Done.  {len(changed)} file(s) fixed,  {len(skipped)} already clean.")
    if changed:
        print(f"\n  Fixed files:")
        for name in changed:
            print(f"    - {name}")
        print(f"\n  Backups saved as .py.bak in the same folder.")
    print("=" * 52)
    input("\n  Press Enter to close...")


if __name__ == "__main__":
    main()
