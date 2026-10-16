"""Exercise the rendered workbench's event handlers without a browser dependency."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import capture_execution_case
from gwtlang.workbench import render_workbench_html


class ElementTree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {"attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = {"attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(element)
        if tag not in {"meta", "link", "input", "br", "hr", "img"}:
            self.stack.append(element)

    def handle_endtag(self, tag):
        if tag not in {"meta", "link", "input", "br", "hr", "img"}:
            self.stack.pop()


@unittest.skipUnless(shutil.which("node"), "Node is needed for workbench interaction checks")
class WorkbenchInteractionTests(unittest.TestCase):
    def test_search_groups_and_filters_preserve_access_to_every_case(self):
        old = Path("examples/refund_review/stage0.gwt")
        new = Path("examples/refund_review/stage1.gwt")
        facts = {"days": 10, "damaged": True, "receipt": False, "clearance": False, "member": False}
        inputs = [facts, {**facts, "days": 46}, {**facts, "damaged": False}]
        cases = [capture_execution_case(old, {"facts": value}, request="assess refund") for value in inputs]
        comparison = compare_execution_cases(old, new, cases, case_references=["damage-young", "damage-old", "preserved"])
        self.assertEqual(comparison.totals.output_changed, 2)
        self.assertEqual(comparison.totals.path_changed, 1)
        html = render_workbench_html(cases[0], comparison)
        parser = ElementTree()
        parser.feed(html)
        script = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        # Minimal DOM adapter; the actual rendered HTML and production script are
        # the inputs. These checks test event behavior, not browser layout.
        harness = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
function build(raw) {
  const attrs = raw.attrs;
  const node = {
    hidden: Object.hasOwn(attrs, 'hidden'),
    open: Object.hasOwn(attrs, 'open'),
    id: attrs.id || '', value: '', textContent: '', events: {},
    getAttribute: (key) => attrs[key] ?? null,
    setAttribute: (key, value) => { attrs[key] = value; },
    classList: { toggle() {} },
    addEventListener(type, callback) { this.events[type] = callback; },
    querySelectorAll(selector) {
      const match = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
      if (!match) throw new Error('unsupported selector: ' + selector);
      const all = [];
      for (const child of this.children) {
        if (Object.hasOwn(child.attrs, match[1]) && (match[2] === undefined || child.attrs[match[1]] === match[2])) all.push(child);
        all.push(...child.querySelectorAll(selector));
      }
      return all;
    },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    attrs,
  };
  node.children = raw.children.map(build);
  return node;
}
const document = build(input.tree);
vm.runInNewContext(input.script, { document });
const choices = document.querySelectorAll('[data-case-choice]');
const groups = document.querySelectorAll('[data-impact-group]');
const panels = document.querySelectorAll('[data-case-panel]');
const search = document.querySelector('[data-case-search]');
const pathQueue = document.querySelector('[data-path-queue]');
const empty = document.querySelector('[data-no-matches]');
const visible = () => choices.filter(x => !x.hidden);
const filter = value => document.querySelector(`[data-filter="${value}"]`).events.click();
const query = value => { search.value = value; search.events.input(); };
assert.equal(choices.length, 3);
assert.equal(groups.length, 1);
assert.equal(pathQueue.open, false);
filter('output_changed');
assert.equal(visible().length, 2);
assert.equal(pathQueue.hidden, true);
query('DAMAGE-OLD');
assert.equal(visible().length, 1);
assert.equal(groups[0].querySelector('[data-group-count]').textContent, '1');
assert.equal(panels.filter(x => !x.hidden).length, 1);
assert.equal(panels.find(x => !x.hidden).id, visible()[0].getAttribute('data-target'));
query('/decision/reason');
assert.equal(visible().length, 2);
query('no-such-case');
assert.equal(visible().length, 0);
assert.equal(empty.hidden, false);
assert.equal(groups[0].hidden, true);
assert.equal(panels.filter(x => !x.hidden).length, 0);
query('');
filter('path_changed');
assert.equal(visible().length, 1);
assert.equal(pathQueue.open, true);
assert.equal(pathQueue.hidden, false);
filter('all');
assert.equal(visible().length, 3);
assert.equal(empty.hidden, true);
for (const choice of choices) {
  choice.events.click();
  assert.equal(panels.filter(x => !x.hidden).length, 1);
  assert.equal(panels.find(x => !x.hidden).id, choice.getAttribute('data-target'));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interactions.cjs"
            path.write_text(harness)
            completed = subprocess.run(["node", str(path)], input=json.dumps({"tree": parser.root, "script": script}), text=True, capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
