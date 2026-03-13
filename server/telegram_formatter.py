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
from typing import cast, Any, List

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
            # Use a dummy match since _format_table_internal expects one
            class MockMatch:
                def __init__(self, text): self._text = text
                def group(self, _): return self._text
            
            # Format the table content ONLY (no backticks)
            formatted = _format_table_internal(MockMatch(code.strip()), wrap_in_code=False)
            code_blocks.append(cast(Any, f"```{lang}\n{formatted}\n```"))
        else:
            code_blocks.append(cast(Any, f"```{lang}\n{code}```"))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    # Define the table formatter utility
    def _format_table_internal(match, wrap_in_code=True) -> str:
        table_text = str(match.group(0)).strip()
        lines = [line.strip() for line in table_text.split('\n') if line.strip()]
        if len(lines) < 2: return table_text
        
        def split_row(row: str) -> List[str]:
            cells = [cell.strip() for cell in row.split('|')]
            if len(cells) > 0 and not cells[0]: cells.pop(0)
            if len(cells) > 0 and not cells[-1]: cells.pop(-1)
            return cells

        rows = []
        for line in lines:
            if re.match(r'^\|?[\s\-:|]+\|?$', line): continue
            rows.append(split_row(line))
        
        if not rows: return table_text
        
        num_cols = max(len(row) for row in rows)
        col_widths_dict = {i: 0 for i in range(num_cols)}
        for row in rows:
            for i, cell in enumerate(row):
                if i in col_widths_dict:
                    cell_len = len(cell)
                    if cell_len > col_widths_dict.get(i, 0):
                        col_widths_dict.update({i: cell_len})
        
        formatted_lines = []
        for i, row in enumerate(rows):
            padded_cells = []
            for j in range(num_cols):
                val = row[j] if j < len(row) else ""
                cw = col_widths_dict.get(j, 0)
                padded_cells.append(f" {val.ljust(cw)} ")
            formatted_lines.append("|" + "|".join(padded_cells) + "|")
            if i == 0:
                sep_parts = []
                for w in range(num_cols):
                    sep_parts.append("-" * (col_widths_dict.get(w, 0) + 2))
                sep = "|" + "|".join(sep_parts) + "|"
                formatted_lines.append(sep)
        
        res = "\n".join(formatted_lines)
        if wrap_in_code:
            # We must stash this NEWly created code block so it doesn't get escaped in Step 4
            placeholder = f"\x00CODEBLOCK{len(code_blocks)}\x00"
            code_blocks.append(cast(Any, f"```\n{res}\n```"))
            return f"\n{placeholder}\n"
        return res

    # Match fenced code blocks (```lang ... ```) - now more lenient with opening line
    text = re.sub(
        r'```(\w*)\s*\n(.*?)```',
        _stash_code_block,
        text,
        flags=re.DOTALL
    )

    # ── Step 1: Handle Markdown Tables in the remaining text ──────────────────────
    table_pattern = r'(?m)^ {0,3}\|?.*\|.*\|?.*?\n {0,3}\|?[\s\-:|]+\|[\s\-:|]*\n(?: {0,3}\|?.*\|.*\|?.*?\n?)*'
    text = re.sub(table_pattern, lambda m: _format_table_internal(m, wrap_in_code=True), text)

    # ── Step 2: Extract inline code so it isn't mangled ─────────────────────
    inline_codes = []
    
    def _stash_inline_code(match):
        code = match.group(1)
        placeholder = f"\x00INLINECODE{len(inline_codes)}\x00"
        # Inline code in MarkdownV2: `code` — contents are not escaped
        inline_codes.append(cast(Any, f"`{code}`"))
        return placeholder
    
    text = re.sub(r'`([^`\n]+)`', _stash_inline_code, text)

    # ── Step 3: Extract markdown links [text](url) ─────────────────────────
    links = []
    
    def _stash_link(match):
        link_text = match.group(1)
        url = match.group(2)
        placeholder = f"\x00LINK{len(links)}\x00"
        # MarkdownV2 links: [escaped text](url)
        # Link text needs escaping, URL does NOT (except for `)` and `\`)
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

        # Regular line — apply inline formatting and escape
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

def _apply_inline_formatting(text: str) -> str:
    """
    Convert inline markdown (bold, italic, strikethrough) and escape
    remaining special characters for MarkdownV2.
    """
    if not text:
        return ""

    # Bold: **text** or __text__ → *text* in MarkdownV2
    BOLD_OPEN = "\x01BOPEN\x01"
    BOLD_CLOSE = "\x01BCLOSE\x01"
    
    def _bold_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{BOLD_OPEN}{escaped_inner}{BOLD_CLOSE}"
    
    text = re.sub(r'\*\*(.+?)\*\*', _bold_replace, text)
    text = re.sub(r'__(.+?)__', _bold_replace, text)
    
    # Italic: *text* or _text_ → _text_ in MarkdownV2
    ITALIC_OPEN = "\x01IOPEN\x01"
    ITALIC_CLOSE = "\x01ICLOSE\x01"
    
    def _italic_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{ITALIC_OPEN}{escaped_inner}{ITALIC_CLOSE}"
    
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', _italic_replace, text)
    text = re.sub(r'(?<![A-Za-z0-9])_(?!_)(.+?)(?<!_)_(?![A-Za-z0-9])', _italic_replace, text)
    
    # Strikethrough: ~~text~~ → ~text~ in MarkdownV2
    STRIKE_OPEN = "\x01SOPEN\x01"
    STRIKE_CLOSE = "\x01SCLOSE\x01"
    
    def _strike_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{STRIKE_OPEN}{escaped_inner}{STRIKE_CLOSE}"
    
    text = re.sub(r'~~(.+?)~~', _strike_replace, text)

    # Now escape any remaining special characters that aren't part of formatting.
    # We protect placeholders by splitting the text into segments.
    # Pattern matches any of our protected markers: \x00... \x00, \b, \r, \x01...
    protected_pattern = r'(\x00(?:CODEBLOCK|INLINE|WA_THINKING|WA_CALL)\d+\x00|\b|\r|\x01[A-Z]+\x01)'
    segments = re.split(protected_pattern, text)
    
    result_segments = []
    for seg in segments:
        if not seg:
            continue
        # If it's a protected segment, keep it as is
        if re.match(protected_pattern, seg):
            result_segments.append(seg)
        else:
            # Escape special MarkdownV2 characters in raw text segments
            # We must also handle backticks specifically if they aren't part of a marker
            # though Step 0/1/2 should have stashed them.
            escaped = _escape_mdv2(seg)
            result_segments.append(escaped)
    
    final_text = ''.join(result_segments)
    
    # Restore bold and italic placeholders
    final_text = final_text.replace(BOLD_OPEN, "*")
    final_text = final_text.replace(BOLD_CLOSE, "*")
    final_text = final_text.replace(ITALIC_OPEN, "_")
    final_text = final_text.replace(ITALIC_CLOSE, "_")
    final_text = final_text.replace(STRIKE_OPEN, "~")
    final_text = final_text.replace(STRIKE_CLOSE, "~")
    
    return final_text


def format_for_telegram(text: str) -> str:
    """
    Main entry point. Converts standard markdown text to Telegram MarkdownV2.
    
    Args:
        text: Raw markdown text from the LLM.
        
    Returns:
        MarkdownV2-formatted text safe for Telegram's API.
    """
    if not text:
        return ""
    
    try:
        return _convert_markdown_to_mdv2(text)
    except Exception as e:
        logger.warning(f"MarkdownV2 conversion failed, falling back to escaped plain text: {e}")
        return _escape_mdv2(text)


def smart_chunk(text: str, max_length: int = 4096) -> List[str]:
    """
    Split a long MarkdownV2 message into chunks that respect Telegram's
    4096 character limit, splitting on paragraph boundaries and never
    breaking mid-code-block.
    
    Args:
        text: The MarkdownV2-formatted text.
        max_length: Maximum characters per chunk (Telegram limit is 4096).
        
    Returns:
        A list of message chunks.
    """
    if len(text) <= max_length:
        return [text]
    
    chunks: List[str] = []
    rem_text: str = text
    
    while rem_text:
        # Re-assert for Pyre
        if not isinstance(rem_text, str): break
        
        text_len = len(rem_text)
        if text_len <= max_length:
            chunks.append(rem_text)
            break
        
        # Extract the segment we can work with using regex to keep Pyre happy
        limit_pattern = r'^(.{1,' + str(max_length) + r'})'
        limit_match = re.match(limit_pattern, rem_text, flags=re.DOTALL)
        if not limit_match:
            chunks.append(rem_text)
            break
            
        head = str(limit_match.group(1))
        split_at = len(head)
        
        # Prefer splitting at double newline (paragraph boundary)
        para_break = head.rfind('\n\n')
        if para_break > max_length // 3:
            split_at = para_break
        else:
            # Fall back to single newline
            line_break = head.rfind('\n')
            if line_break > max_length // 3:
                split_at = line_break
        
        # Safety: check we're not splitting inside a code block
        # Use regex to get the prefix up to split_at
        prefix_pattern = r'^(.{0,' + str(split_at) + r'})'
        prefix_match = re.match(prefix_pattern, rem_text, flags=re.DOTALL)
        
        chunk_candidate = ""
        if prefix_match:
            chunk_candidate = str(prefix_match.group(1))
        else:
            chunk_candidate = head # Fallback
            
        if chunk_candidate.count('```') % 2 != 0:
            # We'd split inside a code block — find the start of this code block
            last_code_start = chunk_candidate.rfind('```')
            # Find newline before code (searching in the same chunk_candidate)
            safe_split = chunk_candidate.rfind('\n', 0, last_code_start)
            if safe_split > 0:
                split_at = safe_split
                # Final re-match for the safe split point
                final_pattern = r'^(.{0,' + str(split_at) + r'})'
                final_match = re.match(final_pattern, rem_text, flags=re.DOTALL)
                if final_match:
                    chunk_candidate = str(final_match.group(1))
        
        # Finalize this chunk
        chunks.append(chunk_candidate.rstrip())
        # Update rem_text using regex to remove what we just took
        # We need to re-verify the split point pattern matches exactly what we took
        take_pattern = r'^(.{0,' + str(split_at) + r'})'
        rem_text = re.sub(take_pattern, '', rem_text, count=1, flags=re.DOTALL).lstrip('\n')
    
    return chunks


def strip_markdown(text: str) -> str:
    """
    Completely strip all markdown formatting for plain-text fallback.
    Used when MarkdownV2 parsing fails on Telegram's end.
    """
    if not text:
        return ""
    
    # Remove code block markers
    text = re.sub(r'```\w*\n?', '', text)
    # Remove inline code markers
    text = re.sub(r'`', '', text)
    # Remove bold/italic markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # Remove strikethrough
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    # Convert links to plain text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove heading markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '───────────', text, flags=re.MULTILINE)
    # Clean up escape characters
    text = text.replace('\\', '')
    
    return text.strip()
