//! Portable, exact source snapshots. Compilation and execution never reopen files.
use crate::{
    CompiledProgram,
    program::compile_nodes,
    program_source::{self, MAX_PROGRAM_BYTES, MAX_PROGRAM_NODES, Node},
    source::{Diagnostic, Result, Span},
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::{Component, Path},
};

const MAX_MODULES: usize = 256;
const MAX_BUNDLE_BYTES: usize = 4 * 1_048_576;
const MAX_IMPORT_DEPTH: usize = 64;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceBundle {
    pub entry: String,
    pub modules: BTreeMap<String, String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModuleIdentity {
    pub path: String,
    pub digest: String,
    pub imports: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProgramIdentity {
    pub algorithm: String,
    pub entry: String,
    pub digest: String,
    pub modules: Vec<ModuleIdentity>,
}

fn origin(file: &str) -> Span {
    Span {
        file: file.into(),
        start: 0,
        end: 0,
        line: 1,
        column: 1,
    }
}

fn path_error(span: &Span) -> Diagnostic {
    Diagnostic::new(
        "import_path",
        "expected a relative slash-separated path within the source root",
        span,
    )
}

fn resolve(parent: &str, path: &str, span: &Span) -> Result<String> {
    if path.is_empty()
        || path.starts_with('/')
        || path.ends_with('/')
        || path
            .chars()
            .any(|ch| ch == '\\' || ch == ':' || ch.is_control())
    {
        return Err(path_error(span));
    }
    let mut parts: Vec<_> = parent
        .rsplit_once('/')
        .map_or(Vec::new(), |(dir, _)| dir.split('/').collect());
    for part in path.split('/') {
        match part {
            "" => return Err(path_error(span)),
            "." => (),
            ".." => {
                if parts.pop().is_none() {
                    return Err(path_error(span));
                }
            }
            _ => parts.push(part),
        }
    }
    if parts.is_empty() {
        return Err(path_error(span));
    }
    Ok(parts.join("/"))
}

fn canonical_path(path: &str) -> Result<()> {
    if resolve("", path, &origin(path))? != path {
        return Err(path_error(&origin(path)));
    }
    Ok(())
}

fn import(node: &Node) -> Result<Option<String>> {
    if node.text != "USE" && !node.text.starts_with("USE ") {
        return Ok(None);
    }
    node.leaf()?;
    let (text, span) = node.tail(3)?;
    let path: String = serde_json::from_str(text).map_err(|_| {
        Diagnostic::new("import_path", "USE requires one quoted source path", &span)
    })?;
    Ok(Some(resolve(&node.span.file, &path, &span)?))
}

struct Graph<F> {
    fetch: F,
    modules: BTreeMap<String, String>,
    identities: BTreeMap<String, ModuleIdentity>,
    visiting: BTreeSet<String>,
    merged: Vec<Node>,
    bytes: usize,
    nodes: usize,
}

impl<F: FnMut(&str, &Span) -> Result<String>> Graph<F> {
    fn visit(&mut self, path: &str, site: &Span, depth: usize) -> Result<()> {
        if self.visiting.contains(path) {
            return Err(Diagnostic::new(
                "import_cycle",
                format!("cyclic import of '{path}'"),
                site,
            ));
        }
        if self.modules.contains_key(path) {
            return Ok(());
        }
        if depth >= MAX_IMPORT_DEPTH || self.modules.len() >= MAX_MODULES {
            return Err(Diagnostic::new(
                "source_limit",
                "source closure exceeds 64 import levels or 256 modules",
                site,
            ));
        }
        let source = (self.fetch)(path, site)?;
        self.bytes += source.len();
        if self.bytes > MAX_BUNDLE_BYTES {
            return Err(Diagnostic::new(
                "source_limit",
                "source closure exceeds four MiB",
                site,
            ));
        }
        let nodes = program_source::parse(&source, path)?;
        let mut pending: Vec<_> = nodes.iter().collect();
        while let Some(node) = pending.pop() {
            self.nodes += 1;
            if self.nodes > MAX_PROGRAM_NODES {
                return Err(node.error("source_limit", "source closure exceeds 16384 source nodes"));
            }
            pending.extend(&node.children);
            for child in &node.children {
                if child.text == "USE" || child.text.starts_with("USE ") {
                    return Err(child.error("import_scope", "USE is only allowed at module scope"));
                }
            }
        }
        let mut imports = Vec::new();
        for node in &nodes {
            if let Some(dependency) = import(node)? {
                imports.push((dependency, node.span.clone()));
            }
        }
        self.identities.insert(
            path.into(),
            ModuleIdentity {
                path: path.into(),
                digest: digest(source.as_bytes()),
                imports: imports.iter().map(|(path, _)| path.clone()).collect(),
            },
        );
        self.modules.insert(path.into(), source);
        self.visiting.insert(path.into());
        for (dependency, span) in imports {
            self.visit(&dependency, &span, depth + 1)?;
        }
        self.visiting.remove(path);
        let nodes: Vec<_> = nodes
            .into_iter()
            .filter(|node| !(node.text == "USE" || node.text.starts_with("USE ")))
            .collect();
        if depth == 0 {
            self.merged.extend(nodes);
        } else {
            let sections = crate::scenario_source::sections(nodes)?;
            let mut headers = 0;
            for node in sections.declarations {
                if node.text.starts_with("PROGRAM ") {
                    node.leaf()?;
                    headers += 1;
                    if headers > 1 {
                        return Err(
                            node.error("duplicate_program", "only one PROGRAM header is allowed")
                        );
                    }
                } else {
                    self.merged.push(node);
                }
            }
            // Imported examples are not semantically checked or run, but malformed
            // module-level forms must not disappear into an apparently valid import.
            for node in sections.background.iter().chain(
                sections
                    .scenarios
                    .iter()
                    .flat_map(|scenario| &scenario.nodes),
            ) {
                if !["GIVEN ", "AND ", "WHEN ", "REQUEST ", "THEN "]
                    .iter()
                    .any(|prefix| node.text.starts_with(prefix))
                {
                    return Err(node.error(
                        "unsupported_module_form",
                        "unsupported imported source form",
                    ));
                }
            }
        }
        Ok(())
    }
}

fn graph<F: FnMut(&str, &Span) -> Result<String>>(entry: &str, fetch: F) -> Result<Graph<F>> {
    canonical_path(entry)?;
    let mut graph = Graph {
        fetch,
        modules: BTreeMap::new(),
        identities: BTreeMap::new(),
        visiting: BTreeSet::new(),
        merged: Vec::new(),
        bytes: 0,
        nodes: 0,
    };
    graph.visit(entry, &origin(entry), 0)?;
    Ok(graph)
}

fn digest(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

fn identity(entry: &str, modules: Vec<ModuleIdentity>) -> ProgramIdentity {
    // A versioned, unambiguous byte encoding; no dependence on JSON formatting.
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-program-sha256-v1\0");
    fn field(hash: &mut Sha256, text: &str) {
        hash.update((text.len() as u64).to_be_bytes());
        hash.update(text.as_bytes());
    }
    field(&mut hash, entry);
    hash.update((modules.len() as u64).to_be_bytes());
    for module in &modules {
        field(&mut hash, &module.path);
        field(&mut hash, &module.digest);
        hash.update((module.imports.len() as u64).to_be_bytes());
        for import in &module.imports {
            field(&mut hash, import);
        }
    }
    ProgramIdentity {
        algorithm: "gwt-native-program-sha256-v1".into(),
        entry: entry.into(),
        digest: format!("sha256:{:x}", hash.finalize()),
        modules,
    }
}

/// Compile only the supplied snapshot. Unreachable files are rejected.
pub fn compile_bundle(bundle: &SourceBundle) -> Result<CompiledProgram> {
    if bundle.modules.len() > MAX_MODULES
        || bundle.modules.values().map(String::len).sum::<usize>() > MAX_BUNDLE_BYTES
    {
        return Err(Diagnostic::new(
            "source_limit",
            "source bundle exceeds module or byte limits",
            &origin(&bundle.entry),
        ));
    }
    for path in bundle.modules.keys() {
        canonical_path(path)?;
    }
    let graph = graph(&bundle.entry, |path, site| {
        bundle.modules.get(path).cloned().ok_or_else(|| {
            Diagnostic::new(
                "missing_module",
                format!("source bundle has no '{path}'"),
                site,
            )
        })
    })?;
    if graph.modules.len() != bundle.modules.len() {
        return Err(Diagnostic::new(
            "unused_module",
            "source bundle contains modules outside the entry's import closure",
            &origin(&bundle.entry),
        ));
    }
    if graph.merged.is_empty() {
        return Err(Diagnostic::new(
            "empty_program",
            "source closure has no declarations or executable steps",
            &origin(&bundle.entry),
        ));
    }
    let mut program = compile_nodes(graph.merged, &bundle.entry)?;
    program.span = origin(&bundle.entry);
    program.identity = Some(identity(
        &bundle.entry,
        graph.identities.into_values().collect(),
    ));
    program.bundle = Some(bundle.clone());
    Ok(program)
}

/// Freeze the import closure. With no explicit root, imports stay below the entry's parent.
/// Symlinks below the selected root are rejected to avoid ambiguous module identities.
pub fn load_bundle(entry: &Path, root: Option<&Path>) -> Result<SourceBundle> {
    load_editor_bundle(entry, root, &BTreeMap::new(), None)
}

/// Editor snapshots substitute only canonical source paths below the selected root.
/// Keep successfully read text even if parsing an import later fails.
pub(crate) fn load_editor_bundle(
    entry: &Path,
    root: Option<&Path>,
    overlays: &BTreeMap<String, String>,
    mut observed: Option<&mut BTreeMap<String, String>>,
) -> Result<SourceBundle> {
    let site = origin(&entry.to_string_lossy());
    if overlays.len() > MAX_MODULES
        || overlays.values().map(String::len).sum::<usize>() > MAX_BUNDLE_BYTES
        || overlays
            .values()
            .any(|source| source.len() > MAX_PROGRAM_BYTES)
    {
        return Err(Diagnostic::new(
            "source_limit",
            "editor snapshots exceed source limits",
            &site,
        ));
    }
    for path in overlays.keys() {
        canonical_path(path)?;
    }
    let io_error = |error: std::io::Error| Diagnostic::new("source_io", error.to_string(), &site);
    let cwd = std::env::current_dir().map_err(io_error)?;
    let absolute = if entry.is_absolute() {
        entry.to_path_buf()
    } else {
        cwd.join(entry)
    };
    let selected_root = match root {
        None => absolute
            .parent()
            .ok_or_else(|| path_error(&site))?
            .to_path_buf(),
        Some(root) => {
            if root.is_absolute() {
                root.to_path_buf()
            } else {
                cwd.join(root)
            }
        }
    };
    // Resolve the selected root itself, but preserve the entry's components so a
    // symlink beneath that root cannot silently become a different logical module.
    let relative = absolute
        .strip_prefix(&selected_root)
        .map_err(|_| path_error(&site))?;
    let mut parts = Vec::new();
    for component in relative.components() {
        match component {
            Component::Normal(part) => parts.push(part.to_str().ok_or_else(|| path_error(&site))?),
            Component::CurDir => (),
            _ => return Err(path_error(&site)),
        }
    }
    let entry_name = parts.join("/");
    let root = selected_root.canonicalize().map_err(io_error)?;
    let graph = graph(&entry_name, |path, span| {
        let io_error = |error: std::io::Error| {
            Diagnostic::new("source_io", format!("cannot read '{path}': {error}"), span)
        };
        let mut physical = root.clone();
        for part in path.split('/') {
            physical.push(part);
            match fs::symlink_metadata(&physical) {
                Ok(metadata) if metadata.file_type().is_symlink() => {
                    return Err(Diagnostic::new(
                        "source_symlink",
                        "source paths below the import root cannot contain symlinks",
                        span,
                    ));
                }
                Ok(_) => (),
                Err(error)
                    if error.kind() == std::io::ErrorKind::NotFound
                        && overlays.contains_key(path) => {}
                Err(error) => return Err(io_error(error)),
            }
        }
        if let Some(source) = overlays.get(path) {
            if fs::metadata(&physical).is_ok_and(|metadata| !metadata.is_file()) {
                return Err(Diagnostic::new(
                    "source_io",
                    "source path must be a regular file",
                    span,
                ));
            }
            if let Some(observed) = observed.as_deref_mut() {
                observed.insert(path.into(), source.clone());
            }
            return Ok(source.clone());
        }
        if !fs::metadata(&physical).map_err(io_error)?.is_file() {
            return Err(Diagnostic::new(
                "source_io",
                "source path must be a regular file",
                span,
            ));
        }
        let mut bytes = Vec::new();
        fs::File::open(&physical)
            .map_err(io_error)?
            .take(MAX_PROGRAM_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(io_error)?;
        if bytes.len() > MAX_PROGRAM_BYTES {
            return Err(Diagnostic::new(
                "source_limit",
                "module source exceeds one MiB",
                span,
            ));
        }
        let source = String::from_utf8(bytes)
            .map_err(|_| Diagnostic::new("source_encoding", "source must be UTF-8", span))?;
        if let Some(observed) = observed.as_deref_mut() {
            observed.insert(path.into(), source.clone());
        }
        Ok(source)
    })?;
    Ok(SourceBundle {
        entry: entry_name,
        modules: graph.modules,
    })
}

pub fn compile_file(entry: &Path, root: Option<&Path>) -> Result<CompiledProgram> {
    compile_bundle(&load_bundle(entry, root)?)
}
