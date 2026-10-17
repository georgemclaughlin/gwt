#!/bin/sh
set -eu
node /opt/playwright-cli/playwright-cli.js -s=gwt-wasm-webkit open http://127.0.0.1:8904/index.html --config /home/g/code/gwt/evaluations/native_browser/2026-10-16-finite/webkit-container-config.json
trap 'node /opt/playwright-cli/playwright-cli.js -s=gwt-wasm-webkit close' EXIT
node /opt/playwright-cli/playwright-cli.js -s=gwt-wasm-webkit run-code --filename /home/g/code/gwt/evaluations/native_browser/2026-10-16-finite/webkit-check.js --json
