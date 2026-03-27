from __future__ import annotations
"""
Telegram MarkdownV2 Formatter for Goku.

Converts standard LLM markdown output into Telegram-compatible MarkdownV2.
Handles escaping, heading conversion, code block preservation, bullet points,
links, and smart message chunking.

Reference: https://core.telegram.org/bots/api#markdownv2-style
"""

import re
import logging
import time
from typing import cast, Any, List, Optional

logger = logging.getLogger(__name__)

# Characters that MUST be escaped in MarkdownV2 outside of code blocks
_SPECIAL_CHARS = r'_[]()~`>#+=|{}.!-'

def _escape_mdv2(text: str) -> str:
    """Escape special MarkdownV2 characters in plain text segments."""
    return re.sub(r'([\_\[\]\(\)\~\`\>\#\+\=\|\{\}\.\!\-])', r'\\\1', text)


def _convert_markdown_to_mdv2(text: str) -> str:
    """
    Convert standard LLM markdown into Telegram MarkdownV2 format.
    
    Strategy: Parse the text block-by-block (code blocks are preserved verbatim),
    then apply inline formatting conversions to non-code segments.
    """

    # ── Step 0: Extract code blocks so they aren't mangled ──────────────────
    code_blocks: list[str] = []
    
    def _stash_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        code = match.group(2)
        
        # Check if this code block is actually a table.
        # If so, we want to align it properly (calculate widths).
        if re.search(r'\|.*\|', code):
            # Format the table content ONLY (no backticks)
            formatted = _format_table_internal(code.strip())
            code_blocks.append(cast(Any, f"```{lang}\n{formatted}\n```"))
        else:
            code_blocks.append(cast(Any, f"```{lang}\n{code}```"))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    # Match fenced code blocks (```lang ... ```)
    text = re.sub(
        r'```(\w*)\s*\n(.*?)```',
        _stash_code_block,
        text,
        flags=re.DOTALL
    )

    # ── Step 1: Handle Markdown Tables in the remaining text ──────────────────────
    table_pattern = r'(?m)^ {0,3}(?:\|?.*\|.*\|?.*?)\n {0,3}\|?[\s\-:|]+\|[\s\-:|]*\n(?: {0,3}\|?.*\|.*\|?.*?\n?)*'
    
    def _format_table_match(match: re.Match) -> str:
        res = _format_table_internal(match.group(0))
        # Stash the table as a code block to protect it from escaping
        placeholder = f"\x00CODEBLOCK{len(code_blocks)}\x00"
        code_blocks.append(cast(Any, f"```\n{res}\n```"))
        return f"\n{placeholder}\n"

    text = re.sub(table_pattern, _format_table_match, text)

    # ── Step 2: Extract inline code so it isn't mangled ─────────────────────
    inline_codes = []
    
    def _stash_inline_code(match: re.Match) -> str:
        code = match.group(1)
        placeholder = f"\x00INLINECODE{len(inline_codes)}\x00"
        # Inline code in MarkdownV2: `code` — contents are not escaped
        inline_codes.append(cast(Any, f"`{code}`"))
        return placeholder
    
    text = re.sub(r'`([^`\n]+)`', _stash_inline_code, text)

    # ── Step 3: Extract markdown links [text](url) ─────────────────────────
    links = []
    
    def _stash_link(match: re.Match) -> str:
        link_text = match.group(1)
        url = match.group(2)
        placeholder = f"\x00LINK{len(links)}\x00"
        # MarkdownV2 links: [escaped text](url)
        escaped_text = _escape_mdv2(link_text)
        safe_url = url.replace('\\', '\\\\').replace(')', '\\)')
        links.append(cast(Any, f"[{escaped_text}]({safe_url})"))
        return placeholder
    
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _stash_link, text)

    # ── Step 4: Process line-by-line for block-level formatting ─────────────
    lines = text.split('\n')
    converted_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            converted_lines.append("")
            continue
            
        # Check if line is a placeholder - if so, don't apply inline formatting to it
        if re.match(r'^\x00(CODEBLOCK|INLINECODE|LINK)\d+\x00$', stripped):
            converted_lines.append(cast(Any, stripped))
            continue

        # Headings → Bold uppercase
        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            escaped = _escape_mdv2(heading_text)
            converted_lines.append(cast(Any, f"\n*{escaped.upper()}*\n"))
            continue

        # Horizontal rules
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            converted_lines.append(cast(Any, _escape_mdv2("───────────")))
            continue

        # Bullet points: - item, * item, • item
        bullet_match = re.match(r'^[\-\*•]\s+(.*)', stripped)
        if bullet_match:
            content = bullet_match.group(1)
            content = _apply_inline_formatting(content)
            converted_lines.append(cast(Any, f"• {content}"))
            continue

        # Numbered lists: 1. item, 2) item
        num_match = re.match(r'^(\d+)[.)]\s+(.*)', stripped)
        if num_match:
            num = num_match.group(1)
            content = num_match.group(2)
            content = _apply_inline_formatting(content)
            converted_lines.append(cast(Any, f"{_escape_mdv2(num)}\\. {content}"))
            continue

        # Regular line — apply inline formatting
        converted_lines.append(cast(Any, _apply_inline_formatting(stripped)))
    
    text = '\n'.join(converted_lines)

    # ── Step 5: Restore stashed elements ────────────────────────────────────
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)
    
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00INLINECODE{i}\x00", code)
    
    for i, link in enumerate(links):
        text = text.replace(f"\x00LINK{i}\x00", link)

    # ── Step 6: Clean up excessive blank lines ──────────────────────────────
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Final safety pass for remaining hashtags
    text = re.sub(r'(?<!\\)#', r'\\#', text)
    
    return text.strip()


def _format_table_internal(table_text: str) -> str:
    """Premium Unicode Table Formatter for Telegram."""
    lines = [line.strip() for line in table_text.split('\n') if line.strip()]
    if len(lines) < 2: return table_text
    
    rows = []
    for line in lines:
        if re.match(r'^\|?[\s\-:|]+\|?$', line): continue
        rows.append(_split_row(line))
    
    if not rows: return table_text
    
    num_cols = max(len(row) for row in rows)
    col_widths: List[int] = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                cell_len = len(cell)
                if cell_len > col_widths[i]:
                    col_widths[i] = cell_len
    
    formatted_lines = []
    
    # Top border
    top = "┌"
    for j in range(num_cols):
        top += "─" * (col_widths[j] + 2)
        if j < num_cols - 1: top += "┬"
    top += "┐"
    formatted_lines.append(top)
    
    for i, row in enumerate(rows):
        padded_cells = []
        for j in range(num_cols):
            val = row[j] if j < len(row) else ""
            cw = col_widths[j]
            padded_cells.append(f" {val.ljust(cw)} ")
        
        formatted_lines.append("│" + "│".join(padded_cells) + "│")
        
        if i == 0: # Header separator
            mid = "├"
            for j in range(num_cols):
                mid += "─" * (col_widths[j] + 2)
                if j < num_cols - 1: mid += "┼"
            mid += "┤"
            formatted_lines.append(mid)
    
    # Bottom border
    bot = "└"
    for j in range(num_cols):
        bot += "─" * (col_widths[j] + 2)
        if j < num_cols - 1: bot += "┴"
    bot += "┘"
    formatted_lines.append(bot)
    
    return "\n".join(formatted_lines)


def _split_row(row: str) -> List[str]:
    """Split markdown table row into cells."""
    cells = [cell.strip() for cell in row.split('|')]
    if len(cells) > 0 and not cells[0]: cells.pop(0)
    if len(cells) > 0 and not cells[-1]: cells.pop(-1)
    return cells


def _apply_inline_formatting(text: str) -> str:
    """Apply inline markdown and escape remaining special chars."""
    if not text:
        return ""

    # Bold: **text** or __text__ → *text* in MarkdownV2
    BOLD_OPEN = "\x01BOPEN\x01"
    BOLD_CLOSE = "\x01BCLOSE\x01"
    
    def _bold_replace(match: re.Match) -> str:
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{BOLD_OPEN}{escaped_inner}{BOLD_CLOSE}"
    
    text = re.sub(r'\*\*(.+?)\*\*', _bold_replace, text)
    text = re.sub(r'__(.+?)__', _bold_replace, text)
    
    # Italic: *text* or _text_ → _text_ in MarkdownV2
    ITALIC_OPEN = "\x01IOPEN\x01"
    ITALIC_CLOSE = "\x01ICLOSE\x01"
    
    def _italic_replace(match: re.Match) -> str:
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{ITALIC_OPEN}{escaped_inner}{ITALIC_CLOSE}"
    
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', _italic_replace, text)
    text = re.sub(r'(?<![A-Za-z0-9])_(?!_)(.+?)(?<!_)_(?![A-Za-z0-9])', _italic_replace, text)
    
    # Strikethrough: ~~text~~ → ~text~ in MarkdownV2
    STRIKE_OPEN = "\x01SOPEN\x01"
    STRIKE_CLOSE = "\x01SCLOSE\x01"
    
    def _strike_replace(match: re.Match) -> str:
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{STRIKE_OPEN}{escaped_inner}{STRIKE_CLOSE}"
    
    text = re.sub(r'~~(.+?)~~', _strike_replace, text)

    # Escape remaining special characters
    protected_pattern = r'(\x00(?:CODEBLOCK|INLINE|LINK)\d+\x00|\x01[A-Z]+\x01)'
    segments = re.split(protected_pattern, text)
    
    result_segments = []
    for seg in segments:
        if not seg: continue
        if re.match(protected_pattern, seg):
            result_segments.append(seg)
        else:
            result_segments.append(_escape_mdv2(seg))
    
    final_text = ''.join(result_segments)
    
    # Restore placeholders
    final_text = final_text.replace(BOLD_OPEN, "*")
    final_text = final_text.replace(BOLD_CLOSE, "*")
    final_text = final_text.replace(ITALIC_OPEN, "_")
    final_text = final_text.replace(ITALIC_CLOSE, "_")
    final_text = final_text.replace(STRIKE_OPEN, "~")
    final_text = final_text.replace(STRIKE_CLOSE, "~")
    
    return final_text


def format_for_telegram(text: str) -> str:
    """Main entry point for Telegram formatting."""
    if not text:
        return ""
    
    try:
        return _convert_markdown_to_mdv2(text)
    except Exception as e:
        logger.warning(f"MarkdownV2 conversion failed: {e}")
        return _escape_mdv2(text)


def smart_chunk(text: str, max_length: int = 4096) -> List[str]:
    """Split long MarkdownV2 message into chunks."""
    if len(text) <= max_length:
        return [text]
    
    chunks: List[str] = []
    rem_text: str = text
    
    while rem_text:
        if not isinstance(rem_text, str): break
        
        text_len = len(rem_text)
        if text_len <= max_length:
            chunks.append(rem_text)
            break
        
        limit_pattern = r'^(.{1,' + str(max_length) + r'})'
        limit_match = re.match(limit_pattern, rem_text, flags=re.DOTALL)
        if not limit_match:
            chunks.append(rem_text)
            break
            
        head = str(limit_match.group(1))
        split_at = len(head)
        
        para_break = head.rfind('\n\n')
        if para_break > max_length // 3:
            split_at = para_break
        else:
            line_break = head.rfind('\n')
            if line_break > max_length // 3:
                split_at = line_break
        
        prefix_pattern = r'^(.{0,' + str(split_at) + r'})'
        prefix_match = re.match(prefix_pattern, rem_text, flags=re.DOTALL)
        
        chunk_candidate = str(prefix_match.group(1)) if prefix_match else head
            
        if chunk_candidate.count('```') % 2 != 0:
            last_code_start = chunk_candidate.rfind('```')
            safe_split = chunk_candidate.rfind('\n', 0, last_code_start)
            if safe_split > 0:
                split_at = safe_split
                final_pattern = r'^(.{0,' + str(split_at) + r'})'
                final_match = re.match(final_pattern, rem_text, flags=re.DOTALL)
                if final_match:
                    chunk_candidate = str(final_match.group(1))
        
        chunks.append(chunk_candidate.rstrip())
        take_pattern = r'^(.{0,' + str(split_at) + r'})'
        rem_text = re.sub(take_pattern, '', rem_text, count=1, flags=re.DOTALL).lstrip('\n')
    
    return chunks


def strip_markdown(text: str) -> str:
    """Fallback plain-text stripping."""
    if not text:
        return ""
    
    text = re.sub(r'```\w*\n?', '', text)
    text = re.sub(r'`', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}\s*$', '───────────', text, flags=re.MULTILINE)
    text = text.replace('\\', '')
    
    return text.strip()
