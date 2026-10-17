#!/bin/sh
# Install an extracted, checksum-verified GWT bundle. No elevated privileges required.
set -eu
prefix="${HOME}/.local"
action=install
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) [ "$#" -ge 2 ] || { echo 'Missing --prefix directory' >&2; exit 1; }; prefix=$2; shift 2 ;;
    --uninstall) action=uninstall; shift ;;
    *) echo 'Usage: sh install.sh [--prefix DIRECTORY] [--uninstall]' >&2; exit 1 ;;
  esac
done
case "$prefix" in /*) ;; *) echo 'Use an absolute installation prefix.' >&2; exit 1 ;; esac
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
destination="$prefix/bin/gwt"
is_gwt() {
  "$1" version --json 2>/dev/null | grep -Eq '"kind"[[:space:]]*:[[:space:]]*"gwt.native-version"'
}
if [ -e "$destination" ] || [ -L "$destination" ]; then
  if ! is_gwt "$destination"; then
    echo "Refusing to replace or remove a different program at $destination." >&2
    echo 'If this is the old Python GWT, uninstall gwtlang with its Python environment first.' >&2
    exit 1
  fi
elif [ "$action" = uninstall ]; then
  echo "GWT is not installed at $destination."
  exit 0
fi
if [ "$action" = uninstall ]; then
  rm -- "$destination"
  echo "Removed $destination."
  exit 0
fi
is_gwt "$bundle/bin/gwt" || { echo 'The bundle does not contain a runnable Rust GWT executable.' >&2; exit 1; }
mkdir -p -- "$prefix/bin"
# Rename a fresh file so upgrades do not truncate a running executable or follow a symlink.
staged=$(mktemp "$prefix/bin/.gwt-install.XXXXXX")
trap 'rm -f -- "$staged"' EXIT HUP INT TERM
cp -- "$bundle/bin/gwt" "$staged"
chmod 755 "$staged"
mv -f -- "$staged" "$destination"
echo "Installed $destination."
resolved=$(command -v gwt || true)
if [ "$resolved" != "$destination" ]; then
  echo "Add $prefix/bin before other GWT installations on PATH, then run: gwt version --json"
  if [ -n "$resolved" ]; then echo "Your current shell resolves gwt to: $resolved"; fi
fi
"$destination" version --json
