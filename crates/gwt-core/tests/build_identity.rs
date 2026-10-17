use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path};

#[test]
fn source_identity_uses_only_self_contained_build_inputs() {
    fn visit(root: &Path, directory: &Path, fields: &mut BTreeMap<Vec<String>, Vec<u8>>) {
        for entry in fs::read_dir(directory).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                visit(root, &path, fields);
            } else {
                fields.insert(
                    path.strip_prefix(root)
                        .unwrap()
                        .components()
                        .map(|part| part.as_os_str().to_str().unwrap().to_owned())
                        .collect(),
                    fs::read(&path).unwrap(),
                );
            }
        }
    }
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut fields = BTreeMap::new();
    visit(root, &root.join("src"), &mut fields);
    for name in ["build.rs", "Cargo.toml", "engine-dependencies.lock"] {
        fields.insert(vec![name.into()], fs::read(root.join(name)).unwrap());
    }
    assert!(
        fields
            .keys()
            .any(|parts| parts.last().unwrap() == "corpus.js")
    );
    assert!(
        fields
            .keys()
            .any(|parts| parts.last().unwrap() == "review.css")
    );
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-engine-source-v2\0");
    for (parts, content) in fields {
        let path = parts.join("/");
        for bytes in [path.as_bytes(), &content] {
            hash.update((bytes.len() as u64).to_be_bytes());
            hash.update(bytes);
        }
    }
    assert_eq!(
        gwt_core::engine_identity().source_digest,
        format!("sha256:{:x}", hash.finalize())
    );
}

#[test]
fn dependency_baseline_matches_the_repository_qualification_lock() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    assert_eq!(
        fs::read(root.join("engine-dependencies.lock")).unwrap(),
        fs::read(root.join("../../Cargo.lock")).unwrap(),
        "dependency changes require updating the packaged baseline and rerunning host qualification"
    );
}
