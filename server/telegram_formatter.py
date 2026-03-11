"""
Telegram MarkdownV2 Formatter for Goku.

Converts standard LLM markdown output into Telegram-compatible MarkdownV2.
Handles escaping, heading conversion, code block preservation, bullet points,
links, and smart message chunking.

Reference: https://core.telegram.org/bots/api#markdownv2-style
"""

import re
import logging

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

    # ── Step 1: Extract code blocks so they aren't mangled ──────────────────
    code_blocks = []
    
    def _stash_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        placeholder = f"\x00CODEBLOCK{len(code_blocks)}\x00"
        # In MarkdownV2, pre-formatted blocks use: ```lang\ncode```
        # Code inside ``` does NOT need escaping.
        code_blocks.append(f"```{lang}\n{code}```")
        return placeholder
    
    # Match fenced code blocks (```lang ... ```)
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        _stash_code_block,
        text,
        flags=re.DOTALL
    )

    # ── Step 2: Extract inline code so it isn't mangled ─────────────────────
    inline_codes = []
    
    def _stash_inline_code(match):
        code = match.group(1)
        placeholder = f"\x00INLINECODE{len(inline_codes)}\x00"
        # Inline code in MarkdownV2: `code` — contents are not escaped
        inline_codes.append(f"`{code}`")
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
        links.append(f"[{escaped_text}]({safe_url})")
        return placeholder
    
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _stash_link, text)

    # ── Step 4: Process line-by-line for block-level formatting ─────────────
    lines = text.split('\n')
    converted_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Headings → Bold uppercase (Telegram has no heading support)
        heading_match = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            # Escape first, then wrap in bold
            escaped = _escape_mdv2(heading_text)
            converted_lines.append(f"\n*{escaped.upper()}*\n")
            continue

        # Horizontal rules → simple separator
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            converted_lines.append(_escape_mdv2("───────────"))
            continue

        # Bullet points: - item, * item, • item
        bullet_match = re.match(r'^[\-\*•]\s+(.*)', stripped)
        if bullet_match:
            content = bullet_match.group(1)
            content = _apply_inline_formatting(content)
            converted_lines.append(f"• {content}")
            continue

        # Numbered lists: 1. item, 2) item
        num_match = re.match(r'^(\d+)[.)]\s+(.*)', stripped)
        if num_match:
            num = num_match.group(1)
            content = num_match.group(2)
            content = _apply_inline_formatting(content)
            converted_lines.append(f"{_escape_mdv2(num)}\\. {content}")
            continue

        # Regular line — apply inline formatting and escape
        converted_lines.append(_apply_inline_formatting(stripped))
    
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
    
    return text.strip()


def _apply_inline_formatting(text: str) -> str:
    """
    Convert inline markdown (bold, italic, strikethrough) and escape
    remaining special characters for MarkdownV2.
    """
    # Bold: **text** or __text__ → *text* in MarkdownV2
    # We use placeholders so the italic regex doesn't consume our bold markers
    BOLD_OPEN = "\x01BOPEN\x01"
    BOLD_CLOSE = "\x01BCLOSE\x01"
    
    def _bold_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{BOLD_OPEN}{escaped_inner}{BOLD_CLOSE}"
    
    text = re.sub(r'\*\*(.+?)\*\*', _bold_replace, text)
    text = re.sub(r'__(.+?)__', _bold_replace, text)
    
    # Italic: *text* or _text_ → _text_ in MarkdownV2
    # We use placeholders to prevent escaping our italic markers
    ITALIC_OPEN = "\x01IOPEN\x01"
    ITALIC_CLOSE = "\x01ICLOSE\x01"
    
    def _italic_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"{ITALIC_OPEN}{escaped_inner}{ITALIC_CLOSE}"
    
    # Only match single * or _ that aren't already part of ** or __
    # For _, also ensure it's not mid-word (like in snake_case_variables)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', _italic_replace, text)
    text = re.sub(r'(?<![A-Za-z0-9])_(?!_)(.+?)(?<!_)_(?![A-Za-z0-9])', _italic_replace, text)
    
    # Strikethrough: ~~text~~ → ~text~ in MarkdownV2
    def _strike_replace(match):
        inner = match.group(1)
        escaped_inner = _escape_mdv2(inner)
        return f"~{escaped_inner}~"
    
    text = re.sub(r'~~(.+?)~~', _strike_replace, text)

    # Now escape any remaining special characters that aren't part of formatting
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        
        # Skip already-escaped characters
        if ch == '\\' and i + 1 < len(text):
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue
        
        # Skip placeholder bytes
        if ch == '\x01':
            result.append(ch)
            i += 1
            continue
        
        # Skip MarkdownV2 formatting markers we just placed
        # Strikethrough: ~...~
        if ch == '~':
            result.append(ch)
            i += 1
            continue
        # Code placeholders (already handled upstream)
        if ch == '`':
            result.append(ch)
            i += 1
            continue
        
        # Escape remaining special chars
        if ch in _SPECIAL_CHARS:
            result.append(f'\\{ch}')
        else:
            result.append(ch)
        
        i += 1
    
    text = ''.join(result)
    
    # Restore bold and italic placeholders to actual MarkdownV2 markers
    text = text.replace(BOLD_OPEN, "*")
    text = text.replace(BOLD_CLOSE, "*")
    text = text.replace(ITALIC_OPEN, "_")
    text = text.replace(ITALIC_CLOSE, "_")
    
    return text


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


def smart_chunk(text: str, max_length: int = 4096) -> list[str]:
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
    
    chunks = []
    remaining = text
    
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        
        # Find a good split point within the limit
        split_at = max_length
        
        # Prefer splitting at double newline (paragraph boundary)
        para_break = remaining.rfind('\n\n', 0, max_length)
        if para_break > max_length // 3:  # Don't split too early
            split_at = para_break
        else:
            # Fall back to single newline
            line_break = remaining.rfind('\n', 0, max_length)
            if line_break > max_length // 3:
                split_at = line_break
        
        # Safety: check we're not splitting inside a code block
        chunk_candidate = remaining[:split_at]
        open_code_blocks = chunk_candidate.count('```')
        if open_code_blocks % 2 != 0:
            # We'd split inside a code block — find the start of this code block
            # and split before it
            last_code_start = chunk_candidate.rfind('```')
            # Look for a newline before the code block
            safe_split = remaining.rfind('\n', 0, last_code_start)
            if safe_split > 0:
                split_at = safe_split
            # else: can't avoid it, split at max_length anyway
        
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip('\n')
    
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
