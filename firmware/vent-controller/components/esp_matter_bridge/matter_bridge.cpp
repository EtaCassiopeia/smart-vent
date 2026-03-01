#include "matter_bridge.h"

#include <esp_log.h>
#include <esp_matter.h>
#include <esp_matter_endpoint.h>
#include <esp_openthread.h>
#include <nvs_flash.h>
#include <esp_mac.h>
#include <app/server/Server.h>
#include <app/server/OnboardingCodesUtil.h>
#include <setup_payload/ManualSetupPayloadGenerator.h>
#include <setup_payload/QRCodeSetupPayloadGenerator.h>

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

    // Derive discriminator from EUI-64 lower 12 bits for unique BLE advertising
    uint8_t mac[8] = {};
    esp_read_mac(mac, ESP_MAC_IEEE802154);
    uint16_t discriminator = ((uint16_t)mac[6] << 4 | (mac[7] >> 4)) & 0x0FFF;
    ESP_LOGI(TAG, "Discriminator derived from EUI-64: %u", discriminator);

    ESP_LOGI(TAG, "Matter node initialized (VID=0xFFF1, PID=0x8001, disc=%u)", discriminator);
    return 0;
}

int matter_bridge_start(void)
{
    ESP_LOGI(TAG, "Configuring OpenThread platform for Matter...");

    // Matter manages the OpenThread stack. Configure the OT platform
    // with native radio (ESP32-C6 built-in 802.15.4) and NVS storage.
    esp_openthread_platform_config_t ot_config = {};
    ot_config.radio_config.radio_mode = RADIO_MODE_NATIVE;
    ot_config.host_config.host_connection_mode = HOST_CONNECTION_MODE_NONE;
    ot_config.port_config.storage_partition_name = "nvs";
    ot_config.port_config.netif_queue_size = 10;
    ot_config.port_config.task_queue_size = 10;
    esp_matter::set_openthread_platform_config(&ot_config);

    ESP_LOGI(TAG, "Starting Matter event loop...");
    esp_err_t err = esp_matter::start(nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_matter::start() failed: %d", err);
        return -1;
    }
    ESP_LOGI(TAG, "Matter started (Thread managed by Matter SDK)");
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
    if (len == 0) return -1;

    chip::SetupPayload payload;
    auto &server = chip::Server::GetInstance();
    auto &commData = server.GetCommissioningWindowManager().GetOpener();

    CHIP_ERROR err = chip::GetManualPairingCode(payload, chip::RendezvousInformationFlags(chip::RendezvousInformationFlag::kBLE));
    if (err != CHIP_NO_ERROR) {
        ESP_LOGW(TAG, "Failed to get manual pairing code");
        buf[0] = '\0';
        return -1;
    }

    std::string code;
    chip::ManualSetupPayloadGenerator generator(payload);
    err = generator.payloadDecimalStringRepresentation(code);
    if (err != CHIP_NO_ERROR) {
        buf[0] = '\0';
        return -1;
    }

    size_t copy_len = code.size() < len - 1 ? code.size() : len - 1;
    memcpy(buf, code.c_str(), copy_len);
    buf[copy_len] = '\0';
    return 0;
}

int matter_bridge_get_qr_payload(char *buf, size_t len)
{
    if (len == 0) return -1;

    chip::SetupPayload payload;
    CHIP_ERROR err = chip::GetQRCodePayload(payload, chip::RendezvousInformationFlags(chip::RendezvousInformationFlag::kBLE));
    if (err != CHIP_NO_ERROR) {
        ESP_LOGW(TAG, "Failed to get QR payload");
        buf[0] = '\0';
        return -1;
    }

    std::string qr;
    chip::QRCodeSetupPayloadGenerator generator(payload);
    err = generator.payloadBase38Representation(qr);
    if (err != CHIP_NO_ERROR) {
        buf[0] = '\0';
        return -1;
    }

    size_t copy_len = qr.size() < len - 1 ? qr.size() : len - 1;
    memcpy(buf, qr.c_str(), copy_len);
    buf[copy_len] = '\0';
    return 0;
}

void matter_bridge_factory_reset(void)
{
    ESP_LOGW(TAG, "Factory reset requested");
    chip::Server::GetInstance().ScheduleFactoryReset();
}
