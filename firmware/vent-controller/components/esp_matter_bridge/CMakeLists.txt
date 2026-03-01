idf_component_register(
    SRCS "matter_bridge.cpp"
    INCLUDE_DIRS "include"
    REQUIRES esp_matter nvs_flash esp_event
)
