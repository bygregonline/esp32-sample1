#include "ml_demo.h"

#include <cstddef>
#include <cstdint>

#include "esp_log.h"
#include "hello_world_model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {

constexpr char TAG[] = "tflm_demo";
constexpr size_t kTensorArenaSize = 4096;
alignas(16) uint8_t tensor_arena[kTensorArenaSize];

const tflite::Model *model = nullptr;
tflite::MicroInterpreter *interpreter = nullptr;
TfLiteTensor *input_tensor = nullptr;
TfLiteTensor *output_tensor = nullptr;

}  // namespace

extern "C" bool ml_demo_init(void) {
    tflite::InitializeTarget();

    model = tflite::GetModel(g_hello_world_float_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "Model schema %u is incompatible with runtime schema %u",
                 static_cast<unsigned>(model->version()),
                 static_cast<unsigned>(TFLITE_SCHEMA_VERSION));
        return false;
    }

    static tflite::MicroMutableOpResolver<1> resolver;
    if (resolver.AddFullyConnected() != kTfLiteOk) {
        ESP_LOGE(TAG, "Failed to register FullyConnected operator");
        return false;
    }

    static tflite::MicroInterpreter static_interpreter(
        model, resolver, tensor_arena, kTensorArenaSize);
    interpreter = &static_interpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "Tensor allocation failed");
        return false;
    }

    input_tensor = interpreter->input(0);
    output_tensor = interpreter->output(0);
    if (input_tensor == nullptr || output_tensor == nullptr ||
        input_tensor->type != kTfLiteFloat32 || output_tensor->type != kTfLiteFloat32 ||
        input_tensor->bytes < sizeof(float) || output_tensor->bytes < sizeof(float)) {
        ESP_LOGE(TAG, "Expected single-value float32 input and output tensors");
        return false;
    }

    ESP_LOGI(TAG, "TensorFlow Lite Micro float32 sine model ready (%u-byte model, %u-byte arena)",
             g_hello_world_float_model_data_len, static_cast<unsigned>(kTensorArenaSize));
    return true;
}

extern "C" bool ml_demo_infer(float input, float *prediction) {
    if (interpreter == nullptr || input_tensor == nullptr || output_tensor == nullptr ||
        prediction == nullptr) {
        return false;
    }

    input_tensor->data.f[0] = input;
    if (interpreter->Invoke() != kTfLiteOk) {
        ESP_LOGE(TAG, "Model inference failed");
        return false;
    }

    *prediction = output_tensor->data.f[0];
    return true;
}
