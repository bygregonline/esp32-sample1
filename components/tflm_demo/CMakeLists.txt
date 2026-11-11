idf_component_register(
    SRCS "ml_demo.cpp" "hello_world_model_data.cc"
    INCLUDE_DIRS "." "include"
    PRIV_REQUIRES esp-tflite-micro bmp280
)
