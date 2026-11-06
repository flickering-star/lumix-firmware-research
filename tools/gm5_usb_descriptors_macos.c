/* Read macOS-cached USB configuration descriptors for a Panasonic USB device.
 *
 * Build: clang -Wno-deprecated-declarations tools/gm5_usb_descriptors_macos.c \
 *          -framework IOKit -framework CoreFoundation -o work/gm5-usb-descriptors
 *
 * Default: GM5 PC baseline, VID 04da / PID 2372. "ptp": PID 2374.
 * "service": historical GH2/FZ30 candidate PID 2370, unverified on GM5.
 * "panasonic": VID 04da with any PID, requiring exactly one matching device.
 * USB IDs alone do not independently establish the camera model.
 * No exclusive device/interface open, driver
 * detach, reset, configuration change, control request or bulk transfer occurs.
 * GetConfigurationDescriptorPtr is documented in Apple's IOUSBLib.h as usable
 * without opening the device. Output omits the camera serial and volume names.
 */

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/usb/IOUSBLib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void number(CFMutableDictionaryRef dict, CFStringRef key, int value) {
    CFNumberRef n = CFNumberCreate(kCFAllocatorDefault, kCFNumberIntType, &value);
    CFDictionarySetValue(dict, key, n);
    CFRelease(n);
}

static int describe(io_service_t service, UInt16 expected_product) {
    IOCFPlugInInterface **plugin = NULL;
    IOUSBDeviceInterface **device = NULL;
    SInt32 score = 0;
    IOReturn result = IOCreatePlugInInterfaceForService(
        service, kIOUSBDeviceUserClientTypeID, kIOCFPlugInInterfaceID, &plugin, &score);
    if (result != kIOReturnSuccess || !plugin) {
        fprintf(stderr, "Could not create descriptor user client: 0x%08x\n", result);
        return 1;
    }
    HRESULT query = (*plugin)->QueryInterface(
        plugin, CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID), (LPVOID *)&device);
    (*plugin)->Release(plugin);
    if (query != S_OK || !device) {
        fprintf(stderr, "Could not get cached-descriptor interface: 0x%08x\n", (unsigned)query);
        return 1;
    }

    UInt16 vendor = 0, product = 0, release = 0;
    UInt8 count = 0;
    if ((*device)->GetDeviceVendor(device, &vendor) ||
        (*device)->GetDeviceProduct(device, &product) ||
        (*device)->GetDeviceReleaseNumber(device, &release) ||
        (*device)->GetNumberOfConfigurations(device, &count) ||
        vendor != 0x04da || (expected_product && product != expected_product) ||
        count == 0 || count > 8) {
        fprintf(stderr, "Device identity/configuration validation failed\n");
        (*device)->Release(device);
        return 1;
    }

    /* Obtain and validate every pointer before emitting any JSON. */
    IOUSBConfigurationDescriptorPtr configs[8] = {0};
    unsigned lengths[8] = {0};
    for (unsigned i = 0; i < count; ++i) {
        result = (*device)->GetConfigurationDescriptorPtr(device, (UInt8)i, &configs[i]);
        if (result || !configs[i]) {
            fprintf(stderr, "Cached configuration %u unavailable: 0x%08x\n", i, result);
            (*device)->Release(device);
            return 1;
        }
        const uint8_t *raw = (const uint8_t *)configs[i];
        lengths[i] = (unsigned)raw[2] | ((unsigned)raw[3] << 8);
        if (raw[0] != 9 || raw[1] != 2 || lengths[i] < 9) {
            fprintf(stderr, "Malformed cached configuration %u\n", i);
            (*device)->Release(device);
            return 1;
        }
        unsigned cursor = 0;
        while (cursor < lengths[i]) {
            if (lengths[i] - cursor < 2 || raw[cursor] < 2 ||
                raw[cursor] > lengths[i] - cursor) {
                fprintf(stderr, "Malformed descriptor boundaries in configuration %u\n", i);
                (*device)->Release(device);
                return 1;
            }
            cursor += raw[cursor];
        }
    }

    printf("{\n  \"vendor_id\": %u,\n  \"product_id\": %u,\n", vendor, product);
    printf("  \"bcd_device\": %u,\n  \"exclusive_open\": false,\n", release);
    printf("  \"model_identity_confirmed\": false,\n");
    printf("  \"configuration_source\": \"IOKit GetConfigurationDescriptorPtr\",\n");
    printf("  \"configurations\": [\n");
    for (unsigned i = 0; i < count; ++i) {
        const uint8_t *raw = (const uint8_t *)configs[i];
        printf("    {\"index\": %u, \"bytes\": %u, \"hex\": \"", i, lengths[i]);
        for (unsigned n = 0; n < lengths[i]; ++n) printf("%02x", raw[n]);
        printf("\"}%s\n", i + 1 == count ? "" : ",");
    }
    printf("  ]\n}\n");
    (*device)->Release(device);
    return 0;
}

int main(int argc, char **argv) {
    UInt16 product = 0x2372;
    if (argc == 2 && strcmp(argv[1], "ptp") == 0) product = 0x2374;
    else if (argc == 2 && strcmp(argv[1], "service") == 0) product = 0x2370;
    else if (argc == 2 && strcmp(argv[1], "panasonic") == 0) product = 0;
    else if (argc != 1) {
        fprintf(stderr, "usage: gm5-usb-descriptors [ptp|service|panasonic]\n");
        return 2;
    }
    CFMutableDictionaryRef match = IOServiceMatching("IOUSBHostDevice");
    if (!match) return 1;
    number(match, CFSTR("idVendor"), 0x04da);
    if (product) number(match, CFSTR("idProduct"), product);
    io_iterator_t iterator = IO_OBJECT_NULL;
    IOReturn result = IOServiceGetMatchingServices(kIOMainPortDefault, match, &iterator);
    if (result) {
        fprintf(stderr, "Device enumeration failed: 0x%08x\n", result);
        return 1;
    }
    io_service_t service = IOIteratorNext(iterator);
    io_service_t extra = IOIteratorNext(iterator);
    IOObjectRelease(iterator);
    if (!service || extra) {
        fprintf(stderr, "Expected exactly one Panasonic USB device matching the filter\n");
        if (service) IOObjectRelease(service);
        if (extra) IOObjectRelease(extra);
        return 1;
    }
    int status = describe(service, product);
    IOObjectRelease(service);
    return status;
}
