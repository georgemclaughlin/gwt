"""Build-time syntax coloring for public examples; never changes source text."""
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path

TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\#[^\n]*|<[A-Za-z_][\w]*>|--[\w-]+|\b\d+(?:\.\d+)?\b|[A-Za-z_][\w]*|<=|>=|!=|==|[<>|=]')
KEYWORDS = set('PROGRAM RECORD REQUEST OUTPUT GIVEN WHEN THEN AND REQUIRE DECIDE ELSE BACKGROUND SCENARIO EXAMPLES IF FOR RETURN LET PASS'.split())
TYPES = set('integer decimal boolean text string list table'.split())
COMMANDS = set('gwt git cd sh export rustup cargo python'.split())


def highlight(source, language):
    parts = []
    end = 0
    for match in TOKENS.finditer(source):
        parts.append(html.escape(source[end:match.start()], quote=False))
        token = match.group()
        kind = None
        if token.startswith(('"', "'")):
            kind = 'key' if language == 'json' and source[match.end():].lstrip().startswith(':') else 'string'
        elif token.startswith('#') and language != 'json':
            kind = 'comment'
        elif token[0].isdigit():
            kind = 'number'
        elif token in {'true', 'false', 'null'}:
            kind = 'bool'
        elif language == 'gwt':
            if token in KEYWORDS:
                kind = 'kw'
            elif token in TYPES or token[0].isupper():
                kind = 'type'
            elif token.startswith('<') and token.endswith('>'):
                kind = 'param'
            elif token in {'set', 'to', 'is', 'into', 'for'}:
                kind = 'action'
        elif language == 'sh':
            if token in COMMANDS and not source[:match.start()].rsplit('\n', 1)[-1].strip():
                kind = 'kw'
            elif token.startswith('--'):
                kind = 'key'
        escaped = html.escape(token, quote=False)
        parts.append(f'<span class="tok-{kind}">{escaped}</span>' if kind else escaped)
        end = match.end()
    parts.append(html.escape(source[end:], quote=False))
    return ''.join(parts)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(markup):
    parser = PlainText()
    parser.feed(markup)
    return ''.join(parser.parts)


def highlight_page(page):
    """Refresh explicitly tagged static examples, preserving copyable source."""
    return re.sub(r'(<code data-language="(gwt|sh|json)">)(.*?)</code>',
                  lambda m: m[1] + highlight(plain_text(m[3]), m[2]) + '</code>',
                  page, flags=re.S)


def highlight_review(page):
    """Color generated JSON/source blocks, including the case templates."""
    def replace(match):
        source = html.unescape(match[2])
        try:
            json.loads(source)
            language = 'json'
        except ValueError:
            language = 'gwt'
        return match[1] + highlight(source, language) + '</pre>'
    page = re.sub(r'(<pre\b[^>]*>)(.*?)</pre>', replace, page, flags=re.S)
    page = re.sub(r'(<span class=step-source>)(.*?)</span>',
                  lambda m: m[1] + highlight(html.unescape(m[2]), 'gwt') + '</span>',
                  page, flags=re.S)
    # The review uses light code surfaces and must remain self-contained offline.
    styles = '''<style data-syntax-highlighting>
.tok-kw{color:#175e47;font-weight:750}.tok-key{color:#244e89}
.tok-string{color:#825009}.tok-number,.tok-param{color:#005d78}
.tok-type,.tok-bool{color:#67408c}.tok-action{color:#364c43;font-weight:650}
.tok-comment{color:#53665b}
</style>'''
    return page.replace('</style>', '</style>' + styles, 1)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pages', nargs='+', type=Path)
    for path in parser.parse_args().pages:
        path.write_text(highlight_page(path.read_text()))
