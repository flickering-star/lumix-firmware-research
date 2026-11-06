/* Offline, host-only codec for the recovered Panasonic five-round AES-CBC.
 * No camera I/O, container packaging, signing or flash-writing capability.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t box[256], inverse[256], products[4][256];

static uint8_t multiply(uint8_t a, uint8_t b) {
    uint8_t result = 0;
    for (unsigned i = 0; i < 8; i++) {
        if (b & 1) result ^= a;
        a = (uint8_t)((a << 1) ^ ((a & 128) ? 0x11b : 0));
        b >>= 1;
    }
    return result;
}

static uint8_t rotate(uint8_t value, unsigned count) {
    return (uint8_t)((value << count) | (value >> (8-count)));
}

static void initialize_tables(void) {
    static const uint8_t factors[4] = {14, 11, 13, 9};
    for (unsigned value = 0; value < 256; value++) {
        uint8_t reciprocal = value ? 1 : 0;
        for (unsigned power = 0; power < 254; power++)
            reciprocal = multiply(reciprocal, (uint8_t)value);
        uint8_t mapped = reciprocal ^ rotate(reciprocal, 1)
            ^ rotate(reciprocal, 2) ^ rotate(reciprocal, 3)
            ^ rotate(reciprocal, 4) ^ 0x63;
        box[value] = mapped;
        inverse[mapped] = (uint8_t)value;
        for (unsigned factor = 0; factor < 4; factor++)
            products[factor][value] = multiply((uint8_t)value, factors[factor]);
    }
}

static void expand_key(const uint8_t key[16], uint8_t schedule[176], unsigned rounds) {
    memcpy(schedule, key, 16);
    uint8_t constant = 1;
    for (unsigned position = 16; position < 16*(rounds+1); position += 4) {
        uint8_t temporary[4];
        memcpy(temporary, schedule+position-4, 4);
        if (position % 16 == 0) {
            uint8_t first = temporary[0];
            for (unsigned i = 0; i < 3; i++) temporary[i] = box[temporary[i+1]];
            temporary[3] = box[first];
            temporary[0] ^= constant;
            constant = multiply(constant, 2);
        }
        for (unsigned i = 0; i < 4; i++)
            schedule[position+i] = schedule[position-16+i] ^ temporary[i];
    }
}

static void decrypt_block(const uint8_t input[16], uint8_t output[16],
                          const uint8_t schedule[176], unsigned rounds) {
    uint8_t state[16], temporary[16];
    for (unsigned i = 0; i < 16; i++) state[i] = input[i] ^ schedule[16*rounds+i];
    for (int round = (int)rounds-1; round >= 0; round--) {
        for (unsigned i = 0; i < 16; i++)
            temporary[i] = inverse[state[(i+16-4*(i%4))%16]] ^ schedule[16*round+i];
        if (round == 0) {
            memcpy(state, temporary, 16);
        } else {
            for (unsigned column = 0; column < 16; column += 4)
                for (unsigned row = 0; row < 4; row++)
                    state[column+row] = products[0][temporary[column+row]]
                        ^ products[1][temporary[column+(row+1)%4]]
                        ^ products[2][temporary[column+(row+2)%4]]
                        ^ products[3][temporary[column+(row+3)%4]];
        }
    }
    memcpy(output, state, 16);
}

static void encrypt_block(const uint8_t input[16], uint8_t output[16],
                          const uint8_t schedule[176], unsigned rounds) {
    uint8_t state[16], shifted[16];
    for (unsigned i = 0; i < 16; i++) state[i] = input[i] ^ schedule[i];
    for (unsigned round = 1; round <= rounds; round++) {
        for (unsigned i = 0; i < 16; i++)
            shifted[i] = box[state[(i+4*(i%4))%16]];
        if (round == rounds) {
            memcpy(state, shifted, 16);
        } else {
            for (unsigned column = 0; column < 16; column += 4)
                for (unsigned row = 0; row < 4; row++)
                    state[column+row] = multiply(shifted[column+row], 2)
                        ^ multiply(shifted[column+(row+1)%4], 3)
                        ^ shifted[column+(row+2)%4] ^ shifted[column+(row+3)%4];
        }
        for (unsigned i = 0; i < 16; i++) state[i] ^= schedule[16*round+i];
    }
    memcpy(output, state, 16);
}

static int hex16(const char *text, uint8_t output[16]) {
    if (strlen(text) != 32) return 0;
    for (unsigned i = 0; i < 16; i++) {
        unsigned value = 0;
        for (unsigned j = 0; j < 2; j++) {
            unsigned char character = (unsigned char)text[2*i+j];
            unsigned digit;
            if (character >= '0' && character <= '9') digit = character-'0';
            else if (character >= 'a' && character <= 'f') digit = character-'a'+10;
            else if (character >= 'A' && character <= 'F') digit = character-'A'+10;
            else return 0;
            value = 16*value+digit;
        }
        output[i] = (uint8_t)value;
    }
    return 1;
}

static int selftest(void) {
    uint8_t key[16], ciphertext[16], expected[16], schedule[176], actual[16];
    if (!hex16("000102030405060708090a0b0c0d0e0f", key)
        || !hex16("69c4e0d86a7b0430d8cdb78070b4c55a", ciphertext)
        || !hex16("00112233445566778899aabbccddeeff", expected)) return 0;
    expand_key(key, schedule, 10);
    decrypt_block(ciphertext, actual, schedule, 10);
    if (memcmp(actual, expected, 16)) return 0;
    encrypt_block(expected, actual, schedule, 10);
    if (memcmp(actual, ciphertext, 16)) return 0;
    /* Independent physical GM1 prefix: expected block equals raw plaintext XOR IV. */
    if (!hex16("350481b566d22d5b89dc46775e644622", key)
        || !hex16("147069b0d8d7a35b439688d2b8e59278", ciphertext)
        || !hex16("cd6a60a6c34c6893a76ad12db4d8bdf2", expected)) return 0;
    expand_key(key, schedule, 5);
    decrypt_block(ciphertext, actual, schedule, 5);
    if (memcmp(actual, expected, 16)) return 0;
    encrypt_block(expected, actual, schedule, 5);
    if (memcmp(actual, ciphertext, 16)) return 0;
    for (unsigned i = 0; i < 256; i++)
        if (inverse[box[i]] != i) return 0;
    return 1;
}

static int quantity(const char *text, unsigned long long *result) {
    if (*text == '-' || !*text) return 0;
    errno = 0;
    char *end = NULL;
    *result = strtoull(text, &end, 0);
    return !errno && end != text && *end == 0;
}

static uint8_t *read_small_file(const char *path, size_t maximum, size_t *length) {
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    uint8_t *data = NULL;
    if (fseek(file, 0, SEEK_END)) goto done;
    long extent = ftell(file);
    if (extent < 0 || (unsigned long)extent > maximum || fseek(file, 0, SEEK_SET)) goto done;
    data = malloc((size_t)extent+1);
    if (!data) goto done;
    if (fread(data, 1, (size_t)extent, file) != (size_t)extent) {
        free(data); data = NULL; goto done;
    }
    *length = (size_t)extent;
done:
    if (fclose(file)) { free(data); data = NULL; }
    return data;
}

static int scan_window(char **argv) {
    uint8_t iv[16];
    size_t window_bytes = 0, cipher_bytes = 0, plain_bytes = 0;
    if (!hex16(argv[5], iv)) return 2;
    uint8_t *window = read_small_file(argv[2], 16*1024*1024, &window_bytes);
    uint8_t *ciphertext = read_small_file(argv[3], 64, &cipher_bytes);
    uint8_t *plaintext = read_small_file(argv[4], 64, &plain_bytes);
    if (!window || !ciphertext || !plaintext || window_bytes < 16 || cipher_bytes != 64 || plain_bytes != 64) {
        free(window); free(ciphertext); free(plaintext);
        fputs("Scan requires a 16-byte to 16-MiB window and two exact 64-byte controls.\n", stderr);
        return 2;
    }
    uint8_t schedule[176], block[16], expected[16];
    for (unsigned i = 0; i < 16; i++) expected[i] = plaintext[i] ^ iv[i];
    unsigned matches = 0;
    printf("{\"schema\":1,\"algorithm\":\"five-round AES-128-CBC\",\"windows_tested\":%zu,\"matches\":[",
           window_bytes-15);
    for (size_t position = 0; position+16 <= window_bytes; position++) {
        expand_key(window+position, schedule, 5);
        decrypt_block(ciphertext, block, schedule, 5);
        if (memcmp(block, expected, 16)) continue;
        int equal = 1;
        for (unsigned offset = 16; offset < 64 && equal; offset += 16) {
            decrypt_block(ciphertext+offset, block, schedule, 5);
            for (unsigned i = 0; i < 16; i++)
                if ((block[i] ^ ciphertext[offset-16+i]) != plaintext[offset+i]) equal = 0;
        }
        if (!equal) continue;
        printf("%s{\"offset\":%zu,\"key_hex\":\"", matches ? "," : "", position);
        for (unsigned i = 0; i < 16; i++) printf("%02x", window[position+i]);
        printf("\",\"all_64_bytes_match\":true}");
        matches++;
    }
    printf("],\"match_count\":%u}\n", matches);
    free(window); free(ciphertext); free(plaintext);
    return matches == 1 ? 0 : 1;
}

int main(int argc, char **argv) {
    initialize_tables();
    if (!selftest()) { fputs("AES self-test failed\n", stderr); return 1; }
    if (argc == 2 && !strcmp(argv[1], "--selftest")) {
        puts("Encryption/decryption: NIST AES-128, physical GM1 five-round block and substitution tables verified.");
        return 0;
    }
    if (argc == 6 && !strcmp(argv[1], "--scan-window")) return scan_window(argv);
    int encrypt = argc > 1 && !strcmp(argv[1], "--encrypt");
    if (encrypt) { argc--; argv++; }
    uint8_t key[16], previous[16];
    unsigned long long offset = 0, length = 0;
    if (argc != 7 || !hex16(argv[3], key) || !hex16(argv[4], previous)
        || !quantity(argv[5], &offset) || !quantity(argv[6], &length)
        || !length || length%16 || offset > 0x7fffffffULL
        || length > 0x7fffffffULL || offset+length > 0x7fffffffULL) {
        fputs("Usage: panasonic-aes5 [--encrypt] INPUT NEW_OUTPUT KEY_HEX IV_HEX OFFSET LENGTH\n", stderr);
        return 2;
    }
    FILE *input = fopen(argv[1], "rb");
    if (!input) { perror("input"); return 1; }
    if (fseek(input, 0, SEEK_END) || ftell(input) < (long)(offset+length)
        || fseek(input, (long)offset, SEEK_SET)) {
        fputs("Input range unavailable\n", stderr); fclose(input); return 1;
    }
    FILE *output = fopen(argv[2], "wbx");
    if (!output) { perror("new output"); fclose(input); return 1; }
    uint8_t schedule[176], block[16], transformed[16];
    expand_key(key, schedule, 5);
    int status = 0;
    for (unsigned long long position = 0; position < length; position += 16) {
        if (fread(block, 1, 16, input) != 16) { status = 1; break; }
        if (encrypt) {
            for (unsigned i = 0; i < 16; i++) block[i] ^= previous[i];
            encrypt_block(block, transformed, schedule, 5);
            memcpy(previous, transformed, 16);
        } else {
            decrypt_block(block, transformed, schedule, 5);
            for (unsigned i = 0; i < 16; i++) transformed[i] ^= previous[i];
            memcpy(previous, block, 16);
        }
        if (fwrite(transformed, 1, 16, output) != 16) { status = 1; break; }
    }
    if (fclose(output)) status = 1;
    if (fclose(input)) status = 1;
    if (status) { fputs("Codec I/O failed; output is incomplete\n", stderr); return 1; }
    printf("%s %llu bytes with five-round AES-128-CBC.\n", encrypt ? "Encoded" : "Decoded", length);
    return 0;
}
