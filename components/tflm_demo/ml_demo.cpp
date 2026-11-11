#include "ml_demo.h"
#include "bmp280_bridge.h"
#include "bmp280.h"

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

static bmp280_t bmp_sensor{};
static bmp280_params_t bmp_params{};
static bool bmp_ready = false;
extern "C" bool monitor_bmp280_init(void) {
    if (i2cdev_init() != ESP_OK || bmp280_init_default_params(&bmp_params) != ESP_OK) return false;
    const uint8_t addresses[] = {BMP280_I2C_ADDRESS_0, BMP280_I2C_ADDRESS_1};
    for (uint8_t address : addresses) {
        if (bmp280_init_desc(&bmp_sensor, address, I2C_NUM_1, GPIO_NUM_1, GPIO_NUM_2) == ESP_OK) {
            if (bmp280_init(&bmp_sensor,&bmp_params)==ESP_OK) { bmp_ready=true; return true; }
            bmp280_free_desc(&bmp_sensor);
        }
    }
    return false;
}
extern "C" bool monitor_bmp280_read(float *pressure_hpa) {
    float temperature=0, pressure_pa=0;
    if (!bmp_ready || !pressure_hpa || bmp280_read_float(&bmp_sensor,&temperature,&pressure_pa,nullptr)!=ESP_OK) return false;
    *pressure_hpa=pressure_pa/100.0f; return true;
}
