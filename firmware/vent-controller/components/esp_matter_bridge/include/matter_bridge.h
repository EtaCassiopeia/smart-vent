#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Callback invoked when a Matter controller sets the target position.
 * @param percent100ths Target position in 0–10000 (100ths of a percent)
 * @param ctx User context pointer passed to matter_bridge_init()
 */
typedef void (*matter_position_cb_t)(uint16_t percent100ths, void *ctx);

/**
 * Callback invoked when a Matter controller triggers the Identify cluster.
 * @param duration_s Identify duration in seconds
 * @param ctx User context pointer passed to matter_bridge_init()
 */
typedef void (*matter_identify_cb_t)(uint16_t duration_s, void *ctx);

/**
 * Initialize the Matter node with a Window Covering endpoint.
 * Must be called before matter_bridge_start().
 *
 * @param position_cb Called when controller changes target position
 * @param identify_cb Called when controller triggers identify
 * @param ctx User context forwarded to callbacks
 * @return 0 on success, non-zero on failure
 */
int matter_bridge_init(matter_position_cb_t position_cb,
                       matter_identify_cb_t identify_cb,
                       void *ctx);

/**
 * Start the Matter event loop. This must be called after matter_bridge_init().
 * Matter will manage the OpenThread stack internally.
 * @return 0 on success, non-zero on failure
 */
int matter_bridge_start(void);

/**
 * Report the current vent position to the Matter fabric.
 * @param percent100ths Current position in 0–10000
 */
void matter_bridge_update_position(uint16_t percent100ths);

/**
 * Report operational status (moving / stopped).
 * @param status 0 = stopped, non-zero = moving
 */
void matter_bridge_update_operational_status(uint8_t status);

/**
 * Check if the device has been commissioned into a Matter fabric.
 * @return true if commissioned
 */
bool matter_bridge_is_commissioned(void);

/**
 * Get the manual pairing code string (e.g. "34970112332").
 * @param buf Output buffer
 * @param len Buffer length
 * @return 0 on success, non-zero if not yet available
 */
int matter_bridge_get_pairing_code(char *buf, size_t len);

/**
 * Get the QR code payload string (e.g. "MT:...").
 * @param buf Output buffer
 * @param len Buffer length
 * @return 0 on success, non-zero if not yet available
 */
int matter_bridge_get_qr_payload(char *buf, size_t len);

/**
 * Factory-reset Matter state: clear fabrics, restart BLE advertising.
 */
void matter_bridge_factory_reset(void);

#ifdef __cplusplus
}
#endif
