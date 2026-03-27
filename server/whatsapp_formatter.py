from __future__ import annotations
"""
WhatsApp Formatter

Converts standard LLM markdown to WhatsApp-friendly formatting.

WhatsApp Markdown:
*bold*
_italic_
~strikethrough~
```code```
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)


def format_for_whatsapp(text: str) -> str:
    """Main entry point."""
    if not text:
        return ""

    try:
        return _convert_to_whatsapp(text)
    except Exception as e:
        logger.warning(f"Formatter failed, sending plain text: {e}")
        return _strip_markdown(text)


def _convert_to_whatsapp(text: str) -> str:
    # ── 1. Preserve existing code blocks ─────────────────────────────────────
    # We must stash these FIRST to prevent other formatting (bold, tables) from mangling them.
    # We also strip language tags (e.g. ```python) which WhatsApp doesn't support.
    code_blocks = []

    def stash_code(m: re.Match) -> str:
        # Group 1: language hint (if any)
        # Group 2: inner content
        content = m.group(2).strip()
        
        # Check if content looks like a table - if so, we want to align it properly
        # but NOT double-wrap it in backticks later.
        if re.search(r'\|.*\|', content):
            # Format the table content ONLY (no backticks)
            formatted = _format_table_internal(content)
            code_blocks.append(f"```\n{formatted}\n```")
        else:
            # WhatsApp doesn't support ```python, it just wants ```
            code_blocks.append(f"```\n{content}\n```")
            
        return f"\x00CODE{len(code_blocks)-1}\x00"

    # Regex: 
    # - ```+ matches at least 3 backticks
    # - \s*(\w*)\s* matches optional language tag with optional spaces
    # - \n? matches optional newline
    # - (.*?) matches content (non-greedy, DOTALL handles newlines)
    # - ```+ matches closing backticks
    text = re.sub(r"```+\s*(\w*)\s*\n?(.*?)```+", stash_code, text, flags=re.DOTALL)

    # ── 2. Convert Markdown tables (remaining text outside blocks) ───────────
    # Matches markdown tables regardless of leading/trailing pipes
    table_pattern = r'(?m)^ {0,3}(?:\|?.*\|.*\|?.*?)\n {0,3}\|?[\s\-:|]+\|[\s\-:|]*\n(?: {0,3}\|?.*\|.*\|?.*?\n?)*'

    def format_table_match(match: re.Match) -> str:
        res = _format_table_internal(match.group(0))
        return f"\n```\n{res}\n```\n"

    text = re.sub(table_pattern, format_table_match, text)

    # ── 3. Preserve inline code (`) ───────────────────────────────────────────
    inline_codes = []

    def stash_inline(m: re.Match) -> str:
        inline_codes.append(m.group(0))
        return f"\x00INLINE{len(inline_codes)-1}\x00"

    text = re.sub(r'`[^`\n]+`', stash_inline, text)

    # ── 4. Standard Markdown formatting (WhatsApp flavor) ────────────────────
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'__(.+?)__', r'*\1*', text, flags=re.DOTALL)

    # Italic (SnakeCase safe)
    text = re.sub(r'(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])', r'_\1_', text, flags=re.DOTALL)

    # Strikethrough
    text = re.sub(r'~~(.+?)~~', r'~\1~', text, flags=re.DOTALL)

    # Headings -> Bold Upper
    def convert_heading(m: re.Match) -> str:
        return f"\n*{m.group(1).strip().upper()}*\n"
    text = re.sub(r'^#{1,6}\s+(.*)', convert_heading, text, flags=re.MULTILINE)

    # Horizontal Rules
    text = re.sub(r'^[-*_]{3,}\s*$', '───────────', text, flags=re.MULTILINE)

    # Links: [text](url) -> text (url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)

    # Bullet lists -> •
    text = re.sub(r'^[\-\*•]\s+', '• ', text, flags=re.MULTILINE)

    # ── 5. Restoration ───────────────────────────────────────────────────────
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODE{i}\x00", block)

    for i, inline in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", inline)

    # ── 6. Normalization ─────────────────────────────────────────────────────
    # Normalize line endings and excessive blank lines
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _format_table_internal(table_text: str) -> str:
    """Premium Unicode Table Formatter."""
    lines = [l.strip() for l in table_text.split("\n") if l.strip()]
    if len(lines) < 2: return table_text
    
    rows = []
    for line in lines:
        # Skip separator line |---|
        if re.match(r'^\|?[\s\-:|]+\|?$', line): continue
        rows.append(_split_row(line))
    
    if not rows: return table_text
    
    col_count = max(len(r) for r in rows)
    # Use list for widths to avoid dict indexing lints
    widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                cell_len = len(cell)
                if cell_len > widths[i]:
                    widths[i] = cell_len
    
    formatted = []
    
    # Top border
    top = "┌"
    for j in range(col_count):
        top += "─" * (widths[j] + 2)
        if j < col_count - 1: top += "┬"
    top += "┐"
    formatted.append(top)
    
    for i, row in enumerate(rows):
        padded = []
        for j in range(col_count):
            val = row[j] if j < len(row) else ""
            w = widths[j]
            padded.append(f" {val.ljust(w)} ")
        
        formatted.append("│" + "│".join(padded) + "│")
        
        if i == 0: # Header separator
            mid = "├"
            for j in range(col_count):
                mid += "─" * (widths[j] + 2)
                if j < col_count - 1: mid += "┼"
            mid += "┤"
            formatted.append(mid)
    
    # Bottom border
    bot = "└"
    for j in range(col_count):
        bot += "─" * (widths[j] + 2)
        if j < col_count - 1: bot += "┴"
    bot += "┘"
    formatted.append(bot)
            
    return "\n".join(formatted)


def _split_row(line: str) -> List[str]:
    """Split markdown table row into cells."""
    cells = [c.strip() for c in line.split("|")]
    # Remove empty leading/trailing cells if present
    if cells and not cells[0]: cells.pop(0)
    if cells and not cells[-1]: cells.pop(-1)
    return cells


def _strip_markdown(text: str) -> str:
    """Fallback plain text."""
    text = re.sub(r'```\w*\n?', '', text)
    text = re.sub(r'`', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()
