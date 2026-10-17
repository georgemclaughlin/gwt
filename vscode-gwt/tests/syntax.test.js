const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const {Registry, INITIAL} = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');

const ready = (async () => {
  const wasm = fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm'));
  await oniguruma.loadWASM(wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength));
  const grammar = JSON.parse(fs.readFileSync(path.join(__dirname, '../syntaxes/gwt.tmLanguage.json'), 'utf8'));
  const registry = new Registry({onigLib: Promise.resolve({createOnigScanner: p => new oniguruma.OnigScanner(p), createOnigString: s => new oniguruma.OnigString(s)}), loadGrammar: async () => grammar});
  return registry.loadGrammar('source.gwt');
})();

async function scope(line, text) {
  const grammar = await ready;
  const offset = line.indexOf(text);
  assert.ok(offset >= 0);
  return grammar.tokenizeLine(line, INITIAL).tokens.find(t => t.startIndex <= offset && offset < t.endIndex).scopes.join(' ');
}

test('real TextMate tokenizer colors native actions and structure in context', async () => {
  for (const action of ['set', 'add', 'subtract', 'append', 'count', 'sum', 'divide', 'print']) {
    assert.match(await scope(`  ${action} value`, action), /support.function.builtin.gwt/);
    assert.match(await scope(`WHEN ${action} value`, action), /support.function.builtin.gwt/);
  }
  for (const keyword of ['USE', 'TYPE', 'FIND', 'DEPENDING', 'LET', 'RETURN', 'DECIDE']) {
    assert.match(await scope(`${keyword} value`, keyword), /keyword.control.gwt/);
  }
  assert.match(await scope('  DEPENDING ON state', 'ON'), /keyword.control.gwt/);
  for (const filter of ['WHERE', 'where']) assert.match(await scope(`  FIND item in items ${filter} true`, filter), /keyword.control.gwt/);
  assert.match(await scope('  item: optional<integer>', 'optional'), /storage.type.gwt/);
  assert.match(await scope('  item: optional<integer>', 'integer'), /storage.type.gwt/);
  assert.doesNotMatch(await scope('  item: optional<integer>', '<integer>'), /variable.parameter/);
  assert.match(await scope('  REQUIRE item is present', 'present'), /keyword.operator.gwt/);
});

test('names, comments, strings and retired forms do not masquerade as native syntax', async () => {
  assert.match(await scope('RECORD parcel', 'parcel'), /storage.type.gwt/);
  assert.match(await scope('  WHEN: integer', 'WHEN'), /variable.other.property.gwt/);
  assert.doesNotMatch(await scope('WHEN review count for <item>', 'count'), /support.function/);
  assert.doesNotMatch(await scope('WHEN SET target to value', 'SET'), /keyword.control|storage.type|support.function/);
  assert.doesNotMatch(await scope('  set item.WHEN to 1', 'item.WHEN'), /keyword.control/);
  assert.match(await scope('WHEN review <item>', '<item>'), /variable.parameter.gwt/);
  assert.match(await scope('  print "WHEN set # null"', 'WHEN'), /string.quoted.double/);
  assert.match(await scope('# WHEN set', 'WHEN'), /comment/);
  for (const legacy of ['find', 'exists', 'any', 'null', 'string', 'table']) {
    assert.doesNotMatch(await scope(`  ${legacy} value`, legacy), /support.function|storage.type|constant.language/);
  }
  for (const legacy of ['greater than', 'less than', 'at least', 'at most']) {
    assert.doesNotMatch(await scope(`THEN amount ${legacy} 2`, legacy), /keyword.operator/);
  }
});

test('collection-header highlighting does not leak into subsequent domain phrases', async () => {
  const grammar = await ready;
  let state = INITIAL;
  for (const line of ['  FOR item in items WHERE true', '    set total to 2', 'WHEN review where for <item>']) {
    const result = grammar.tokenizeLine(line, state);
    state = result.ruleStack;
    if (line.startsWith('WHEN')) {
      const at = line.indexOf('where');
      const scopes = result.tokens.find(t => t.startIndex <= at && at < t.endIndex).scopes.join(' ');
      assert.doesNotMatch(scopes, /keyword.control/);
    }
  }
});
