"""Server-side sanitization helpers for mail bodies and quotes.

Everything stored as HTML goes through ``clean_html`` before it hits the
database, so rendering with ``|safe`` later can never execute a script.
"""

import html as html_lib
import re

import nh3

from .models import MAIL_TYPE_HTML

ALLOWED_TAGS = {
    'p', 'br', 'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'sub', 'sup',
    'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'a', 'span', 'div', 'pre', 'code',
}

ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
}

_URL_SCHEMES = {'http', 'https', 'mailto'}

_BREAK_RE = re.compile(r'(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</blockquote>')
_BLOCK_END_RE = re.compile(r'(?i)</(ul|ol|table|tr|pre)>')
_TAG_RE = re.compile(r'<[^>]+>')


def clean_html(value):
    """Return *value* with everything outside the allow-list removed."""
    if not value:
        return ''
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=_URL_SCHEMES,
        strip_comments=True,
        link_rel='noopener noreferrer',
    )


def plain_to_html(value):
    """Escape plain text, preserving line breaks as ``<br>``."""
    if not value:
        return ''
    lines = [html_lib.escape(line) for line in value.splitlines()]
    return '<br>\n'.join(lines)


def html_to_text(value):
    """Best-effort conversion of HTML to plain text (previews, notifications)."""
    if not value:
        return ''
    text = _BREAK_RE.sub('\n', value)
    text = _BLOCK_END_RE.sub('\n', text)
    text = _TAG_RE.sub('', text)
    text = html_lib.unescape(text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def message_html(body, mail_type, quoted=''):
    """Render a stored message body (plus its quote history) as safe HTML."""
    if mail_type == MAIL_TYPE_HTML:
        html = clean_html(body)
    else:
        html = plain_to_html(body)
    if quoted:
        html = f'{html}<div class="mail-quote-history">{quoted}</div>'
    return html
