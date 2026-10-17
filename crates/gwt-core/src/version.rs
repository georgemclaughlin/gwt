//! Toolchain identity is separate from a language release or case schema.
use crate::{EngineIdentity, engine_identity};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NativeVersion {
    pub kind: &'static str,
    pub schema_version: u32,
    pub package_name: &'static str,
    pub package_version: &'static str,
    pub language_profile: &'static str,
    pub language_version: Option<&'static str>,
    pub status: &'static str,
    pub engine: EngineIdentity,
}

/// Describe this compiled library without loading or executing a GWT program.
///
/// `language_version` is absent until a native language release is assigned.
/// The experimental profile name does not promise unchanged semantics; use the
/// engine identity and verified cases when comparing particular builds.
pub fn version_info() -> NativeVersion {
    NativeVersion {
        kind: "gwt.native-version",
        schema_version: 1,
        package_name: env!("CARGO_PKG_NAME"),
        package_version: env!("CARGO_PKG_VERSION"),
        language_profile: "gwt-native-experimental",
        language_version: None,
        status: "experimental",
        engine: engine_identity(),
    }
}
