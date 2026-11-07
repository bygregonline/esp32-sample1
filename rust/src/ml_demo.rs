//! FFI wrapper around the shared ESP-IDF TensorFlow Lite Micro demo component.

use std::f32::consts::TAU;

extern "C" {
    fn ml_demo_init() -> bool;
    fn ml_demo_infer(input: f32, prediction: *mut f32) -> bool;
}

pub fn init() -> bool {
    // The C++ component owns the interpreter, model, and statically allocated tensor arena.
    unsafe { ml_demo_init() }
}

pub fn log_prediction(source: &str, input_fraction: f32) {
    let model_input = input_fraction.clamp(0.0, 1.0) * TAU;
    let mut prediction = 0.0_f32;

    if unsafe { ml_demo_infer(model_input, &mut prediction) } {
        log::info!(
            "TFLM demo | input: {} -> {:.3} rad | predicted sin(x): {:.3}",
            source,
            model_input,
            prediction,
        );
    }
}
