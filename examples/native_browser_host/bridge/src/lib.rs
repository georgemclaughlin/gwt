//! Small, bounded, filesystem-free bridge. Each preview uses a fresh worker/instance.
use gwt_core::{ProgramLimits, SourceBundle, compile_bundle, engine_identity};
use serde::Deserialize;
use serde_json::{Value, json};
use std::cell::RefCell;

const MAX_INPUT: usize = 2 * 1_048_576;
const MAX_OUTPUT: usize = 8 * 1_048_576;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    bundle: SourceBundle,
    request: String,
    input: Value,
    limits: ProgramLimits,
}

fn execute(bytes: &[u8]) -> Value {
    let request: Request = match serde_json::from_slice(bytes) {
        Ok(request) => request,
        Err(error) => {
            return json!({"kind":"gwt.browser-error","phase":"input","message":error.to_string()});
        }
    };
    let maximum = ProgramLimits::default();
    if request.limits.execution.steps > maximum.execution.steps
        || request.limits.execution.evidence_bytes > maximum.execution.evidence_bytes
        || request.limits.execution.text_bytes > maximum.execution.text_bytes
        || request.limits.call_depth > maximum.call_depth
    {
        return json!({"kind":"gwt.browser-error","phase":"limits","message":"Preview limits cannot exceed native defaults."});
    }
    match compile_bundle(&request.bundle) {
        Ok(program) => json!({
            "kind":"gwt.browser-preview","schemaVersion":1,"engine":engine_identity(),
            "execution":program.run_request(&request.request,&request.input,request.limits),
        }),
        Err(diagnostic) => {
            json!({"kind":"gwt.browser-error","phase":"check","diagnostic":diagnostic})
        }
    }
}

#[derive(Default)]
struct Buffers {
    input: Vec<u8>,
    output: Vec<u8>,
}

thread_local! { static BUFFERS: RefCell<Buffers> = RefCell::new(Buffers::default()); }

// Bounds-checked word copies avoid passing allocator pointers across the ABI.
// Export names are unique to this standalone bridge.
#[unsafe(no_mangle)]
pub extern "C" fn gwt_reset(length: u32) -> u32 {
    BUFFERS.with(|buffers| {
        let mut buffers = buffers.borrow_mut();
        buffers.input.clear();
        buffers.output.clear();
        if length as usize > MAX_INPUT {
            return 0;
        }
        buffers.input.resize(length as usize, 0);
        1
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn gwt_put(offset: u32, word: u32) -> u32 {
    BUFFERS.with(|buffers| {
        let mut buffers = buffers.borrow_mut();
        let offset = offset as usize;
        if offset >= buffers.input.len() {
            return 0;
        }
        let count = 4.min(buffers.input.len() - offset);
        buffers.input[offset..offset + count].copy_from_slice(&word.to_le_bytes()[..count]);
        1
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn gwt_run() -> u32 {
    BUFFERS.with(|buffers| {
        let mut buffers = buffers.borrow_mut();
        buffers.output = serde_json::to_vec(&execute(&buffers.input)).expect("JSON response");
        if buffers.output.len() > MAX_OUTPUT {
            buffers.output = br#"{"kind":"gwt.browser-error","phase":"output","message":"Preview output exceeds eight MiB."}"#.to_vec();
        }
        buffers.output.len() as u32
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn gwt_get(offset: u32) -> u32 {
    BUFFERS.with(|buffers| {
        let buffers = buffers.borrow();
        let offset = offset as usize;
        if offset >= buffers.output.len() {
            return 0;
        }
        let mut word = [0; 4];
        let count = 4.min(buffers.output.len() - offset);
        word[..count].copy_from_slice(&buffers.output[offset..offset + count]);
        u32::from_le_bytes(word)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn abi_bounds_and_utf8_round_trip() {
        assert_eq!(gwt_reset(MAX_INPUT as u32 + 1), 0);
        assert_eq!(gwt_put(0, 0), 0);
        let bytes = "{\"unknown\":\"🍂\"}".as_bytes();
        assert_eq!(gwt_reset(bytes.len() as u32), 1);
        for (index, chunk) in bytes.chunks(4).enumerate() {
            let mut word = [0; 4];
            word[..chunk.len()].copy_from_slice(chunk);
            assert_eq!(gwt_put(index as u32 * 4, u32::from_le_bytes(word)), 1);
        }
        assert_eq!(gwt_put(bytes.len() as u32, 0), 0);
        let length = gwt_run() as usize;
        let output: Vec<u8> = (0..length)
            .step_by(4)
            .flat_map(|offset| gwt_get(offset as u32).to_le_bytes())
            .take(length)
            .collect();
        let payload: Value = serde_json::from_slice(&output).unwrap();
        assert_eq!(payload["kind"], "gwt.browser-error");
        assert_eq!(payload["phase"], "input");
        assert_eq!(gwt_get(length as u32), 0);
    }
}
