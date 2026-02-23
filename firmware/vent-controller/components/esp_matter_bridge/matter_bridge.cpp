#include "matter_bridge.h"

#include <esp_log.h>
#include <esp_matter.h>
#include <esp_matter_endpoint.h>
#include <app/server/Server.h>

static const char *TAG = "matter_bridge";

using namespace esp_matter;
using namespace esp_matter::endpoint;
using namespace chip::app::Clusters;

// --- Stored callbacks and state ---

static matter_position_cb_t s_position_cb = nullptr;
static matter_identify_cb_t s_identify_cb = nullptr;
static void *s_user_ctx = nullptr;
static uint16_t s_endpoint_id = 0;
static node_t *s_node = nullptr;

// --- Matter attribute update callback ---

static esp_err_t app_attribute_update_cb(
    attribute::callback_type_t type,
    uint16_t endpoint_id,
    uint32_t cluster_id,
    uint32_t attribute_id,
    esp_matter_attr_val_t *val,
    void *priv_data)
{
    if (type != attribute::PRE_UPDATE) {
        return ESP_OK;
    }

    if (endpoint_id != s_endpoint_id) {
        return ESP_OK;
    }

    // WindowCovering cluster: GoToLiftPercentage sets CurrentPositionLiftPercent100ths
    if (cluster_id == WindowCovering::Id) {
        if (attribute_id == WindowCovering::Attributes::TargetPositionLiftPercent100ths::Id) {
            uint16_t pct = val->val.u16;
            ESP_LOGI(TAG, "Matter: target position set to %u/10000", pct);
            if (s_position_cb) {
                s_position_cb(pct, s_user_ctx);
            }
        }
    }

    return ESP_OK;
}

// --- Matter identification callback ---

static esp_err_t app_identification_cb(
    identification::callback_type_t type,
    uint16_t endpoint_id,
    uint8_t effect_id,
    uint8_t effect_variant,
    void *priv_data)
{
    if (type == identification::START) {
        ESP_LOGI(TAG, "Matter: identify START (effect=%u)", effect_id);
        if (s_identify_cb) {
            s_identify_cb(10, s_user_ctx);  // default 10s identify
        }
    } else if (type == identification::STOP) {
        ESP_LOGI(TAG, "Matter: identify STOP");
        if (s_identify_cb) {
            s_identify_cb(0, s_user_ctx);
        }
    }
    return ESP_OK;
}

// --- Public C API ---

int matter_bridge_init(matter_position_cb_t position_cb,
                       matter_identify_cb_t identify_cb,
                       void *ctx)
{
    ESP_LOGI(TAG, "Initializing Matter node...");

    s_position_cb = position_cb;
    s_identify_cb = identify_cb;
    s_user_ctx = ctx;

    // Create Matter node
    node::config_t node_config;
    s_node = node::create(&node_config, app_attribute_update_cb, app_identification_cb);
    if (!s_node) {
        ESP_LOGE(TAG, "Failed to create Matter node");
        return -1;
    }

    // Create Window Covering endpoint
    window_covering_device::config_t wc_config;
    wc_config.window_covering.type = 0;  // Rollershade
    wc_config.window_covering.config_status = 0x00;
    wc_config.window_covering.operational_status = 0;
    wc_config.window_covering.end_product_type = 0;  // Rollershade
    wc_config.window_covering.mode = 0;

    endpoint_t *ep = window_covering_device::create(s_node, &wc_config,
                                                     ENDPOINT_FLAG_NONE, nullptr);
    if (!ep) {
        ESP_LOGE(TAG, "Failed to create Window Covering endpoint");
        return -1;
    }
    s_endpoint_id = endpoint::get_id(ep);
    ESP_LOGI(TAG, "Window Covering endpoint ID: %u", s_endpoint_id);

    // Set Basic Information cluster attributes
    endpoint_t *root_ep = endpoint::get_first(s_node);
    if (root_ep) {
        uint16_t root_id = endpoint::get_id(root_ep);
        cluster_t *basic_cluster = cluster::get(root_ep, BasicInformation::Id);
        if (basic_cluster) {
            // VendorName
            esp_matter_attr_val_t vendor_name = esp_matter_char_str("SmartVent", 9);
            attribute::update(root_id, BasicInformation::Id,
                            BasicInformation::Attributes::VendorName::Id, &vendor_name);

            // ProductName
            esp_matter_attr_val_t product_name = esp_matter_char_str("Smart HVAC Vent", 15);
            attribute::update(root_id, BasicInformation::Id,
                            BasicInformation::Attributes::ProductName::Id, &product_name);
        }
    }

    ESP_LOGI(TAG, "Matter node initialized (VID=0xFFF1, PID=0x8001)");
    return 0;
}

int matter_bridge_start(void)
{
    ESP_LOGI(TAG, "Starting Matter event loop...");
    esp_err_t err = esp_matter::start(nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_matter::start() failed: %d", err);
        return -1;
    }
    ESP_LOGI(TAG, "Matter started");
    return 0;
}

void matter_bridge_update_position(uint16_t percent100ths)
{
    ESP_LOGI(TAG, "Reporting position: %u/10000", percent100ths);

    esp_matter_attr_val_t val = esp_matter_nullable_uint16(percent100ths);
    attribute::update(s_endpoint_id, WindowCovering::Id,
                     WindowCovering::Attributes::CurrentPositionLiftPercent100ths::Id, &val);
}

void matter_bridge_update_operational_status(uint8_t status)
{
    ESP_LOGI(TAG, "Reporting operational status: %u", status);

    esp_matter_attr_val_t val = esp_matter_uint8(status);
    attribute::update(s_endpoint_id, WindowCovering::Id,
                     WindowCovering::Attributes::OperationalStatus::Id, &val);
}

bool matter_bridge_is_commissioned(void)
{
    auto &server = chip::Server::GetInstance();
    return server.GetFabricTable().FabricCount() > 0;
}

int matter_bridge_get_pairing_code(char *buf, size_t len)
{
    // Will be implemented in PR 5 (BLE commissioning)
    ESP_LOGW(TAG, "matter_bridge_get_pairing_code: not yet implemented");
    if (len > 0) buf[0] = '\0';
    return -1;
}

int matter_bridge_get_qr_payload(char *buf, size_t len)
{
    // Will be implemented in PR 5 (BLE commissioning)
    ESP_LOGW(TAG, "matter_bridge_get_qr_payload: not yet implemented");
    if (len > 0) buf[0] = '\0';
    return -1;
}

void matter_bridge_factory_reset(void)
{
    ESP_LOGW(TAG, "Factory reset requested");
    chip::Server::GetInstance().ScheduleFactoryReset();
}
