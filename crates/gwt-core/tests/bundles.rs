use gwt_core::{
    ProgramLimits, SourceBundle, compile_bundle, compile_file, compile_program, load_bundle,
};
use serde_json::json;
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

fn invoice() -> SourceBundle {
    let source = include_str!("fixtures/invoice.gwt");
    let types = source.find("TYPE ").unwrap();
    let request = source.find("REQUEST ").unwrap();
    let behavior = source.find("WHEN price <").unwrap();
    let scenario = source.find("SCENARIO ").unwrap();
    SourceBundle {
        entry: "app/main.gwt".into(),
        modules: BTreeMap::from([
            (
                "app/main.gwt".into(),
                format!(
                    "PROGRAM invoice pricing\nUSE \"../lib/types.gwt\"\nUSE \"../lib/pricing.gwt\"\n{}{}",
                    &source[request..behavior],
                    &source[scenario..]
                ),
            ),
            ("lib/types.gwt".into(), source[types..request].into()),
            (
                "lib/pricing.gwt".into(),
                format!(
                    "PROGRAM pricing library\nUSE \"types.gwt\"\n{}SCENARIO library example\nTHEN false\n",
                    &source[behavior..scenario]
                ),
            ),
        ]),
    }
}

fn run(program: &gwt_core::CompiledProgram) -> gwt_core::ProgramExecution {
    program.run_request(
        "price invoice",
        &json!({"invoice":{"unit_price":"19.95","quantity":2}}),
        ProgramLimits::default(),
    )
}

#[test]
fn diamond_imports_are_deduplicated_and_keep_source_evidence() {
    let bundle = invoice();
    let program = compile_bundle(&bundle).unwrap();
    assert_eq!(program.scenario_names().len(), 2);
    assert!(
        program
            .test_scenarios(ProgramLimits::default())
            .iter()
            .all(|case| case.execution.ok)
    );
    let execution = run(&program);
    assert!(execution.ok);
    assert_eq!(
        execution.result.as_ref().unwrap()["decision"]["total"],
        "47.88"
    );
    assert_eq!(execution.program_identity.as_ref(), program.identity());
    assert_eq!(program.identity().unwrap().modules.len(), 3);
    assert!(
        execution
            .events
            .iter()
            .any(|event| event.span.file == "lib/pricing.gwt")
    );
    for event in &execution.events {
        let source = &bundle.modules[&event.span.file];
        assert!(source.get(event.span.start..event.span.end).is_some());
        assert_eq!(
            source[..event.span.start]
                .bytes()
                .filter(|byte| *byte == b'\n')
                .count()
                + 1,
            event.span.line
        );
    }
    assert_eq!(program.source_bundle(), Some(&bundle));
}

#[test]
fn identities_bind_exact_bytes_edges_and_entry_and_freeze_compilation() {
    let bundle = invoice();
    let program = compile_bundle(&bundle).unwrap();
    let before = program.identity().unwrap().clone();
    let mut changed = bundle.clone();
    changed
        .modules
        .get_mut("lib/pricing.gwt")
        .unwrap()
        .push_str("# reviewed\n");
    assert_ne!(
        compile_bundle(&changed).unwrap().identity().unwrap().digest,
        before.digest
    );
    assert_eq!(program.identity(), Some(&before));
    assert_eq!(program.source_bundle(), Some(&bundle));
    changed
        .modules
        .get_mut("lib/pricing.gwt")
        .unwrap()
        .replace_range(..0, "USE \"types.gwt\"\n");
    let other = compile_bundle(&changed).unwrap();
    assert_eq!(other.identity().unwrap().modules[1].imports.len(), 2);
    assert_eq!(run(&program).result, run(&other).result);
    let round_trip: SourceBundle =
        serde_json::from_str(&serde_json::to_string(&bundle).unwrap()).unwrap();
    assert_eq!(
        compile_bundle(&round_trip).unwrap().identity(),
        Some(&before)
    );
}

#[test]
fn identity_has_an_independent_known_answer() {
    let bundle = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([("main.gwt".into(), "THEN true\n".into())]),
    };
    let program = compile_bundle(&bundle).unwrap();
    // Generated independently using Python hashlib and the documented byte encoding.
    assert_eq!(
        program.identity().unwrap().digest,
        "sha256:be18fc9b73b144dc5fe9f14146e3a8bb676265e1f0547efd866d4e200b71faa5"
    );
    assert_eq!(
        program.identity().unwrap().modules[0].digest,
        "sha256:6395cd4cc0b75b4af9c71dab7389a4fd2dc358c24cf9e73df59e390923f639e6"
    );
}

#[test]
fn imports_reject_missing_cycles_escaping_paths_and_hidden_modules() {
    let mut bundle = invoice();
    bundle.modules.remove("lib/types.gwt");
    let error = compile_bundle(&bundle).unwrap_err();
    assert_eq!(error.code, "missing_module");
    assert_eq!(error.span.file, "app/main.gwt");
    let mut bundle = invoice();
    bundle
        .modules
        .get_mut("lib/types.gwt")
        .unwrap()
        .push_str("USE \"../app/main.gwt\"\n");
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "import_cycle");
    for path in [
        "../../outside.gwt",
        "/outside.gwt",
        "C:/outside.gwt",
        "../lib\\types.gwt",
        "../lib//types.gwt",
        "",
        "../lib/",
        "nul\0.gwt",
    ] {
        let mut bundle = invoice();
        bundle.modules.insert(
            "app/main.gwt".into(),
            format!("USE {}\n", serde_json::to_string(path).unwrap()),
        );
        assert_eq!(
            compile_bundle(&bundle).unwrap_err().code,
            "import_path",
            "{path}"
        );
    }
    let mut bundle = invoice();
    bundle
        .modules
        .insert("unrelated.gwt".into(), "THEN false\n".into());
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "unused_module");
    let mut bundle = invoice();
    bundle
        .modules
        .insert("lib/./alias.gwt".into(), "THEN true\n".into());
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "import_path");
}

#[test]
fn imported_errors_report_the_actual_module_and_collisions_fail() {
    let mut bundle = invoice();
    let body = bundle.modules.get_mut("lib/pricing.gwt").unwrap();
    *body = body.replace(
        "REQUIRE invoice.quantity > 0",
        "REQUIRE invoice.quantity and true",
    );
    let error = compile_bundle(&bundle).unwrap_err();
    assert_eq!(error.code, "type_mismatch");
    assert_eq!(error.span.file, "lib/pricing.gwt");
    assert!(
        bundle.modules[&error.span.file][error.span.start..error.span.end]
            .contains("invoice.quantity")
    );
    let mut bundle = invoice();
    bundle
        .modules
        .get_mut("lib/pricing.gwt")
        .unwrap()
        .push_str("TYPE InvoiceStatus is text\n");
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "duplicate_type");
    for form in [
        "BACKGROUND\n  THEN true\n",
        "USE 123\n",
        "WHEN hidden <x>\n  USE \"types.gwt\"\n",
        "PROGRAM second header\n",
    ] {
        let mut bundle = invoice();
        bundle
            .modules
            .get_mut("lib/pricing.gwt")
            .unwrap()
            .push_str(form);
        assert!(compile_bundle(&bundle).is_err(), "accepted {form}");
    }
    assert_eq!(
        compile_program("USE \"module.gwt\"\n", "main.gwt")
            .unwrap_err()
            .code,
        "imports_require_bundle"
    );
}

struct Directory(PathBuf);
impl Directory {
    fn new(bundle: &SourceBundle) -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-bundle-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        for (name, source) in &bundle.modules {
            let file = path.join(name);
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::write(file, source).unwrap();
        }
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn filesystem_snapshots_survive_relocation_and_later_edits() {
    let bundle = invoice();
    let first = Directory::new(&bundle);
    let second = Directory::new(&bundle);
    let entry = first.0.join(&bundle.entry);
    assert_eq!(load_bundle(&entry, None).unwrap_err().code, "import_path");
    let frozen = load_bundle(&entry, Some(&first.0)).unwrap();
    assert_eq!(frozen, bundle);
    let program = compile_bundle(&frozen).unwrap();
    let relocated = compile_file(&second.0.join(&bundle.entry), Some(&second.0)).unwrap();
    assert_eq!(program.identity(), relocated.identity());
    fs::write(first.0.join("lib/pricing.gwt"), "THEN false\n").unwrap();
    assert_eq!(run(&program).result.unwrap()["decision"]["total"], "47.88");
    assert_eq!(
        compile_bundle(&frozen).unwrap().identity(),
        program.identity()
    );
    assert!(compile_file(&entry, Some(&first.0)).is_err());
    assert!(load_bundle(&entry, Some(&second.0)).is_err());
}

#[test]
fn filesystem_rejects_non_files_invalid_utf8_and_oversized_sources() {
    #[cfg(unix)]
    assert_eq!(
        load_bundle(std::path::Path::new("/"), None)
            .unwrap_err()
            .code,
        "import_path"
    );
    let bundle = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([("main.gwt".into(), "THEN true\n".into())]),
    };
    let dir = Directory::new(&bundle);
    let path = dir.0.join("main.gwt");
    fs::write(&path, [0xff, 0xfe]).unwrap();
    assert_eq!(
        load_bundle(&path, None).unwrap_err().code,
        "source_encoding"
    );
    fs::write(&path, vec![b' '; 1_048_577]).unwrap();
    assert_eq!(load_bundle(&path, None).unwrap_err().code, "source_limit");
    fs::remove_file(&path).unwrap();
    fs::create_dir(&path).unwrap();
    assert_eq!(load_bundle(&path, None).unwrap_err().code, "source_io");
}

#[cfg(unix)]
#[test]
fn filesystem_rejects_file_and_directory_symlinks_below_root() {
    let bundle = invoice();
    let dir = Directory::new(&bundle);
    let entry = dir.0.join(&bundle.entry);
    let types = dir.0.join("lib/types.gwt");
    fs::rename(&types, dir.0.join("actual.gwt")).unwrap();
    std::os::unix::fs::symlink("../actual.gwt", &types).unwrap();
    assert_eq!(
        load_bundle(&entry, Some(&dir.0)).unwrap_err().code,
        "source_symlink"
    );
    fs::remove_file(&types).unwrap();
    fs::rename(dir.0.join("actual.gwt"), &types).unwrap();
    fs::rename(dir.0.join("lib"), dir.0.join("actual")).unwrap();
    std::os::unix::fs::symlink("actual", dir.0.join("lib")).unwrap();
    assert_eq!(
        load_bundle(&entry, Some(&dir.0)).unwrap_err().code,
        "source_symlink"
    );
}

#[test]
fn bundle_limits_cover_depth_module_count_bytes_and_total_nodes() {
    let chain = |count: usize| SourceBundle {
        entry: "0.gwt".into(),
        modules: (0..count)
            .map(|index| {
                (
                    format!("{index}.gwt"),
                    if index + 1 == count {
                        "THEN true\n".into()
                    } else {
                        format!("USE \"{}.gwt\"\n", index + 1)
                    },
                )
            })
            .collect(),
    };
    let mut deepest = chain(64);
    deepest
        .modules
        .insert("63.gwt".into(), "TYPE Fact is text\n".into());
    assert!(compile_bundle(&deepest).is_ok());
    let mut widest = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::new(),
    };
    let mut main = String::new();
    for index in 0..255 {
        main.push_str(&format!("USE \"{index}.gwt\"\n"));
        widest.modules.insert(
            format!("{index}.gwt"),
            format!("TYPE Fact{index} is text\n"),
        );
    }
    widest.modules.insert("main.gwt".into(), main);
    assert!(compile_bundle(&widest).is_ok());
    assert_eq!(compile_bundle(&chain(65)).unwrap_err().code, "source_limit");
    assert_eq!(
        compile_bundle(&chain(257)).unwrap_err().code,
        "source_limit"
    );
    let mut bundle = chain(5);
    for source in bundle.modules.values_mut() {
        source.push_str(&format!("#{}\n", "a".repeat(850_000)));
    }
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "source_limit");
    let mut bundle = chain(2);
    for source in bundle.modules.values_mut() {
        source.push_str(&"THEN true\n".repeat(8200));
    }
    assert_eq!(compile_bundle(&bundle).unwrap_err().code, "source_limit");
}

#[test]
fn cli_uses_explicit_import_root_and_reports_frozen_identity() {
    let bundle = invoice();
    let dir = Directory::new(&bundle);
    let entry = dir.0.join(&bundle.entry);
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("test")
        .arg(&entry)
        .arg("--import-root")
        .arg(&dir.0)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let payload: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["scenarioCount"], 2);
    assert_eq!(payload["programIdentity"]["entry"], bundle.entry);
    assert_eq!(
        payload["programIdentity"],
        payload["scenarios"][0]["execution"]["programIdentity"]
    );
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("check")
        .arg(entry)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let payload: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["diagnostic"]["code"], "import_path");
}
