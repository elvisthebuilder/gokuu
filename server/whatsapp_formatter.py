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
    # WhatsApp natively supports Markdown tables now. We no longer mangle them into Unicode.
    # We just let them pass through.

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
