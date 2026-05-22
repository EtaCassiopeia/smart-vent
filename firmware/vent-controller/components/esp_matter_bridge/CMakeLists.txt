idf_component_register(
    SRCS "matter_bridge.cpp"
    INCLUDE_DIRS "include"
    REQUIRES esp_matter nvs_flash esp_event
)

# The esp_matter component registry package (1.3.x) does not define
# CHIP_HAVE_CONFIG_H, which prevents the CHIP SDK from including the
# generated SystemBuildConfig.h / CHIPProjectConfig.h headers. Without
# these headers, CHIP_SYSTEM_CONFIG_USE_LWIP is never set and the build
# fails. Add the define globally so all CHIP source files pick it up.
idf_build_set_property(COMPILE_OPTIONS "-DCHIP_HAVE_CONFIG_H=1" APPEND)

# ESP-IDF v5.2.3 defaults to -std=gnu++2b (C++23), which exposes
# std::to_underlying and conflicts with chip::to_underlying via ADL.
# Force C++17 which is the CHIP SDK's minimum requirement.
idf_build_set_property(CXX_COMPILE_OPTIONS "-std=gnu++17" APPEND)
