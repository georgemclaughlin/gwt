use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
};

fn collect(directory: &Path, files: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(directory).expect("read native source directory") {
        let path = entry.expect("source directory entry").path();
        if path.is_dir() {
            collect(&path, files);
        } else {
            files.push(path);
        }
    }
}

fn main() {
    let root = PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let mut files = Vec::new();
    collect(&root.join("src"), &mut files);
    files.extend([
        root.join("build.rs"),
        root.join("Cargo.toml"),
        root.join("engine-dependencies.lock"),
    ]);
    files.sort();
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-engine-source-v2\0");
    println!("cargo:rerun-if-changed=src");
    for file in files {
        println!("cargo:rerun-if-changed={}", file.display());
        let name = file
            .strip_prefix(&root)
            .unwrap()
            .to_str()
            .unwrap()
            .replace('\\', "/");
        let bytes = fs::read(&file).expect("read engine source");
        for field in [name.as_bytes(), &bytes] {
            hash.update((field.len() as u64).to_be_bytes());
            hash.update(field);
        }
    }
    println!(
        "cargo:rustc-env=GWT_NATIVE_ENGINE_SOURCE=sha256:{:x}",
        hash.finalize()
    );
}
