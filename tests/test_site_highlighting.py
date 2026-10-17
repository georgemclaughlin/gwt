import html
import json
import re
import unittest
from pathlib import Path

from tools.gwt_syntax import VOCABULARY, tokens, textmate
from tools.highlight_site import highlight, highlight_page, highlight_review, plain_text

ROOT = Path(__file__).resolve().parents[1]


class SiteHighlightingTests(unittest.TestCase):
    def test_highlighting_preserves_exact_copyable_source_and_escapes_html(self):
        examples = {
            'gwt': 'WHEN review <report> into <decision>\n  REQUIRE report.count <= 1500\n  set decision.note to "<script>alert(1)</script> & WHEN"\n# WHEN comment\n',
            'sh': 'gwt run policy.gwt \\\n  --request "quote delivery"\nexport PATH="$HOME/.local/bin:$PATH"\n',
            'json': '{"WHEN": "<img src=x onerror=alert(1)>", "fee": 5, "ok": true}',
        }
        for language, source in examples.items():
            with self.subTest(language=language):
                output = highlight(source, language)
                self.assertEqual(plain_text(output), source)
                self.assertNotIn('<script>', output)
                self.assertNotIn('<img ', output)
                self.assertIn('class="tok-', output)
        self.assertIn('<span class="tok-string">"WHEN"</span>', highlight('"WHEN"', 'gwt'))
        self.assertIn('<span class="tok-key">"fee"</span>', highlight('{"fee": 5}', 'json'))

    def test_native_roles_are_contextual_and_do_not_advertise_retired_forms(self):
        def roles(source):
            return [(source[start:end], role) for start, end, role in tokens(source)]
        for action in ['set', 'add', 'subtract', 'append', 'count', 'sum', 'divide', 'print']:
            self.assertIn((action, 'action'), roles(f'  {action} value'))
            self.assertIn((action, 'action'), roles(f'WHEN {action} value'))
        for head in ['USE', 'TYPE', 'FIND', 'DEPENDING', 'LET', 'RETURN', 'DECIDE']:
            self.assertIn((head, 'kw'), roles(f'{head} name'))
        self.assertIn(('ON', 'kw'), roles('DEPENDING ON state'))
        for word in ['WHERE', 'where']:
            self.assertIn((word, 'kw'), roles(f'FIND item in items {word} true'))
        self.assertIn(('optional', 'type'), roles('value: optional<integer>'))
        self.assertIn(('integer', 'type'), roles('value: optional<integer>'))
        self.assertNotIn(('<integer>', 'param'), roles('value: optional<integer>'))
        self.assertIn(('present', 'operator'), roles('REQUIRE value is present'))
        self.assertIn(('parcel', 'type'), roles('RECORD parcel'))
        self.assertIn(('WHEN', 'key'), roles('  WHEN: integer'))
        self.assertNotIn(('count', 'action'), roles('WHEN review count for <item>'))
        self.assertNotIn(('SET', 'type'), roles('WHEN SET target to value'))
        self.assertNotIn(('WHEN', 'kw'), roles('set item.WHEN to 1'))
        for word in ['find', 'exists', 'any', 'null', 'string', 'table']:
            self.assertEqual(roles(word), [], word)
        self.assertIn('tok-bool', highlight('null', 'json'))
        self.assertNotIn('tok-bool', highlight('null', 'gwt'))
        self.assertNotIn('tok-string', highlight("'text'", 'gwt'))

    def test_checked_in_textmate_grammar_matches_shared_rules(self):
        grammar = json.loads((ROOT / 'vscode-gwt/syntaxes/gwt.tmLanguage.json').read_text())
        self.assertEqual(grammar, textmate())
        self.assertIn(VOCABULARY['filter']['preferred'], VOCABULARY['filter']['accepted'])
        self.assertEqual(set(VOCABULARY['reservedBehaviorHeads']),
                         set(VOCABULARY['actions'] + VOCABULARY['structural']['statement'] + ['find', 'exists']))

    def test_public_examples_are_highlighted_and_refresh_is_idempotent(self):
        for name in ['index.html', 'getting-started.html', 'installation.html']:
            page = (ROOT / 'docs' / name).read_text()
            self.assertEqual(highlight_page(page), page, name)
            for block in re.findall(r'<pre\b[^>]*>(.*?)</pre>', page, re.S):
                self.assertIn('class="tok-', block, name)

    def test_review_templates_and_evidence_text_survive_coloring(self):
        source = 'WHEN check <item>\n  REQUIRE item.weight > 0\n'
        evidence = '{"selected": true, "fee": 5}'
        payload = '<script type="application/json">{"unchanged":true}</script>'
        page = '<style>pre{}</style><template><pre class=source>' + html.escape(source) + '</pre><pre>' + html.escape(evidence) + '</pre></template><span class=step-source>REQUIRE weight &gt; 0</span>' + payload
        result = highlight_review(page)
        blocks = re.findall(r'<pre\b[^>]*>(.*?)</pre>', result, re.S)
        self.assertEqual([plain_text(block) for block in blocks], [source, evidence])
        self.assertTrue(all('class="tok-' in block for block in blocks))
        self.assertIn('<span class=step-source><span class="tok-kw">REQUIRE</span>', result)
        self.assertIn(payload, result)
        self.assertIn('<style data-syntax-highlighting>', result)


if __name__ == '__main__':
    unittest.main()
