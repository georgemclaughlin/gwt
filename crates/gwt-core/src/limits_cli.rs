use gwt_core::ProgramLimits;

/// A complete host-limit object avoids silently inheriting future defaults.
/// Deserialize directly to retain duplicate/unknown-field rejection.
pub fn read(path: &str) -> Result<ProgramLimits, Box<dyn std::error::Error>> {
    let source = super::read_bounded(path, 4096)?;
    serde_json::from_str(&source)
        .map_err(|error| format!("{path}: invalid execution limits: {error}").into())
}
