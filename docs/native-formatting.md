# Native source formatting

The Rust toolchain can format source without Python, loading imports, or running
programs. It normalizes layout while preserving expression text, string and
number spelling, call grouping, statement order, and table values. It uses the
same quote-aware comment and table-cell handling as the native parser.

## Commands

Build from the repository root, then preview or check a file:

```sh
cargo +1.96.0 build --workspace --locked
target/debug/gwt-native format examples/native_delivery/rules.gwt
target/debug/gwt-native format examples/native_delivery/rules.gwt --check
```

All commands emit JSON. The default previews formatted text without writing.
`--check` exits zero only when the file already matches its formatted form;
a needed change returns exit one with `changed: true`. To apply formatting,
explicitly use `gwt-native format FILE.gwt --write`.

Write mode formats and validates first, writes a temporary file in the same
directory, preserves file permissions, checks that source bytes still match,
then renames the temporary file over the source. It refuses symlink file entries
and changed read-only files. A malformed source file is left intact. The
concurrent-change check is best effort; it is not a filesystem transaction.

The library equivalent is `format_source(source, filename)`, returning
`FormattedSource { text, changed }` or a source diagnostic.

## Layout rules and validation

- Code retains two-space indentation and its existing block nesting. The
  formatter refuses invalid indentation rather than dedenting a whole file.
- Leading/trailing blank lines are removed; repeated interior blank lines
  collapse to one. Nonempty output ends with one newline.
- Leading keyword/built-in spacing and field colons are normalized. Internal
  expression spacing and domain phrases are preserved.
- Comments use `# text`, with two spaces before an inline comment. Comment
  placement and indentation are preserved.
- Table columns align across intervening comments or blank lines. Quoted pipes,
  hashes, escaped quotes, and empty quoted strings remain cell contents. Widths
  use Unicode scalar counts; visual width can vary with the editor font.
- Uniform LF or CRLF line endings are retained. Mixed LF/CRLF becomes LF.
  Lone CR line endings are refused.

Validation checks balanced strings/groups, block layout, and scenario/example
table structure before and after formatting. It also checks that the parsed
statement tree and table values remain equivalent under these layout rules.
This is **layout validation**, not a complete grammar or semantic check. For
example, formatting can retain an unfinished expression or an unresolved DTO;
use `gwt-native check` and `gwt-native test` to assess executable programs.
Empty and comment-only buffers can be formatted even though they are not runnable.

Input and output are each limited to one MiB. Formatting permits at most 16,384
physical lines and 256 table columns. Native block/scenario/table limits also
apply. Output growth from table padding is bounded before a file is changed.

Formatting may change source identity and evidence locations. Captured cases
retain their frozen source; formatting does not rewrite them.

## VS Code

With `gwt.engine: "native"`, **Format Document** and **GWT: Format Current File**
use the Rust formatter. Edits stay in the buffer and support undo/redo. They do
not save, compile imports, or execute scenarios. Untitled GWT buffers are also
supported, using the first workspace folder's native settings when available.
The document version and source digest must still match before an edit is
returned; obsolete responses and invalid layout produce no replacement.

## Snapshot protocol

`gwt-native format-editor` reads one stdin JSON request:

```json
{"file": "rules.gwt", "text": "WHEN  print  9007199254740993\n"}
```

It returns `kind: "gwt.native-format"`, `schemaVersion: 1`, `ok`, `sourceDigest`,
`changed`, `text`, and `diagnostic`. The digest hashes the original UTF-8 text.
`text` is a JSON string, so exact numeric spelling is not parsed as host numbers.
On a formatting failure, `text` is null and the diagnostic points into the
original snapshot, including CRLF bytes. The file field is only a source label;
this protocol performs no filesystem reads or writes.

The encoded request is limited to eight MiB and its filename to 4096 bytes.
Unknown fields and malformed JSON are rejected. File CLI responses also include
`mode: "preview"`, `"check"`, or `"write"`.

The [formatting checkpoint](../evaluations/native_editor/2026-10-16-format/README.md)
records Rust tests, native example comparisons, CLI write checks, and actual
VS Code buffer/undo/cancellation tests. It does not establish full IDE support
or comparative human understanding benefits.
