/* Native in-memory bridge to the existing independently checked codec.
 * No filesystem, network, USB or flashing operation is exposed here. */
#define main lumix_existing_codec_cli
#include "../../tools/panasonic_aes5.c"
#undef main

#ifdef _WIN32
#define LUMIX_EXPORT __declspec(dllexport)
#else
#define LUMIX_EXPORT __attribute__((visibility("default")))
#endif

LUMIX_EXPORT int lumix_codec_selftest(void) {
    initialize_tables();
    return selftest() ? 0 : -1;
}

LUMIX_EXPORT int lumix_codec_cbc(const uint8_t *input, uint8_t *output,
                               size_t length, const uint8_t key[16],
                               const uint8_t iv[16], int encrypt) {
    if (!input || !output || !key || !iv || !length || length % 16
        || (encrypt != 0 && encrypt != 1)) return -1;
    uint8_t schedule[176], previous[16], temporary[16], original[16];
    initialize_tables();
    expand_key(key, schedule, 5);
    memcpy(previous, iv, 16);
    for (size_t at = 0; at < length; at += 16) {
        memcpy(original, input + at, 16);
        if (encrypt) {
            for (unsigned i = 0; i < 16; ++i) temporary[i] = original[i] ^ previous[i];
            encrypt_block(temporary, output + at, schedule, 5);
            memcpy(previous, output + at, 16);
        } else {
            decrypt_block(original, temporary, schedule, 5);
            for (unsigned i = 0; i < 16; ++i) output[at + i] = temporary[i] ^ previous[i];
            memcpy(previous, original, 16);
        }
    }
    memset(schedule, 0, sizeof schedule);
    return 0;
}
