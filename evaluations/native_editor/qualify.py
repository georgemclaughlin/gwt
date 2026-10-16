"""Run the installed VS Code extension host with an isolated workspace/profile.

Requires an installed `code`, a graphical session (or Xvfb), extension npm
dependencies, and a built native executable. Never downloads an editor.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine', choices=['native', 'python'], default='native')
    parser.add_argument('--native', type=Path, default=Path('target/debug/gwt-native'))
    parser.add_argument('--code', default='code')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    native = args.native.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    working = Path(tempfile.mkdtemp(prefix='gwt-editor-qualification-'))
    workspace = working / 'workspace'
    (workspace / '.vscode').mkdir(parents=True)
    settings = {'files.autoSave': 'off', 'window.restoreWindows': 'none',
                'extensions.autoUpdate': False, 'update.mode': 'none'}
    if args.engine == 'native':
        settings.update({'gwt.engine': 'native', 'gwt.native.command': str(native)})
        source = ('USE "types.gwt"\nREQUEST echo\n  GIVEN amount is Amount\n'
                  '  WHEN print amount\n  OUTPUT amount is Amount\n'
                  'SCENARIO exact\nGIVEN amount is 9007199254740993\n'
                  'REQUEST echo\nTHEN prints [9007199254740993]\n')
    else:
        # Omit gwt.engine to exercise the installed extension's default.
        source = 'TYPE Amount is integer\nGIVEN amount is 1\nWHEN print amount\nTHEN amount == 1\n'
    (workspace / 'main.gwt').write_text(source)
    (workspace / 'types.gwt').write_text('TYPE Amount is integer\n')
    (workspace / '.vscode/settings.json').write_text(json.dumps(settings))
    command = [args.code, '--new-window', '--user-data-dir', str(working / 'profile'),
               '--extensions-dir', str(working / 'extensions'),
               '--extensionDevelopmentPath=' + str(repo / 'vscode-gwt'),
               '--extensionTestsPath=' + str(repo / 'vscode-gwt/tests/extension-host.js'),
               '--skip-welcome', '--skip-release-notes', '--disable-workspace-trust',
               '--disable-extensions', '--no-sandbox', '--wait', str(workspace)]
    environment = {**os.environ, 'GWT_EDITOR_EVIDENCE': str(output),
                   'GWT_NATIVE_TEST_COMMAND': str(native), 'GWT_EDITOR_ENGINE': args.engine}
    metadata = {'engine': args.engine, 'command': command, 'temporaryDirectory': str(working)}
    extension_files = ['extension.js', 'native-editor.js', 'native-tools.js', 'package.json',
                       'language-configuration.json', 'syntaxes/gwt.tmLanguage.json', 'tests/extension-host.js']
    metadata['extensionSourceSha256'] = {name: hashlib.sha256((repo / 'vscode-gwt' / name).read_bytes()).hexdigest()
                                        for name in extension_files}
    if args.engine == 'native':
        metadata['nativeSha256'] = hashlib.sha256(native.read_bytes()).hexdigest()
    try:
        with (output / 'launcher.log').open('w') as log:
            result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=120, check=False)
        metadata['launcherExitCode'] = result.returncode
        # The installed code launcher can exit zero even when its test fails.
        # Require the success artifact written only after every assertion.
        report = json.loads((output / 'extension-host.json').read_text())
        assert result.returncode == 0 and report['assertionsPassed'] is True
        assert all(hashlib.sha256((repo / 'vscode-gwt' / name).read_bytes()).hexdigest() == digest
                   for name, digest in metadata['extensionSourceSha256'].items()), 'extension source changed during qualification'
        if args.engine == 'native':
            assert hashlib.sha256(native.read_bytes()).hexdigest() == metadata['nativeSha256'], 'native executable changed during qualification'
    finally:
        logs = working / 'profile/logs'
        if logs.exists():
            shutil.copytree(logs, output / 'logs')
        (output / 'qualification.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'ok': True, 'engine': args.engine, 'output': str(output)}))


if __name__ == '__main__':
    main()
