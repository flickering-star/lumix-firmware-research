/* Offline literal-key search using CommonCrypto. No USB or camera operations.
 * Tests AES-128/256 ECB/CBC against a known 64-byte plaintext/ciphertext pair.
 * CBC block two provides an oracle independent of the initial IV. A candidate
 * must then reproduce all 64 bytes; the IV is derived only after that match.
 * This does not test transformed keys, other ciphers/modes or other framing.
 */
#include <CommonCrypto/CommonCryptor.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int decrypt(const uint8_t *input, size_t size, const uint8_t *key, size_t key_size,
                   const uint8_t *iv, int ecb, uint8_t *output) {
    size_t moved = 0;
    CCCryptorStatus status = CCCrypt(kCCDecrypt, kCCAlgorithmAES,
        ecb ? kCCOptionECBMode : 0, key, key_size, iv,
        input, size, output, size, &moved);
    return status == kCCSuccess && moved == size;
}

static uint8_t *read_file(const char *path, size_t *size) {
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    if (fseek(file, 0, SEEK_END)) { fclose(file); return NULL; }
    long length = ftell(file);
    if (length <= 0 || length > 32 * 1024 * 1024 || fseek(file, 0, SEEK_SET)) {
        fclose(file); return NULL;
    }
    uint8_t *data = malloc((size_t)length);
    if (!data || fread(data, 1, (size_t)length, file) != (size_t)length) {
        free(data); fclose(file); return NULL;
    }
    fclose(file); *size = (size_t)length; return data;
}

static void hex(const uint8_t *data, size_t size) {
    for (size_t i = 0; i < size; ++i) printf("%02x", data[i]);
}

static int selftest(void) {
    const uint8_t plain[16] = {0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,
                                0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff};
    const uint8_t encrypted128[16] = {0x69,0xc4,0xe0,0xd8,0x6a,0x7b,0x04,0x30,
                                       0xd8,0xcd,0xb7,0x80,0x70,0xb4,0xc5,0x5a};
    const uint8_t encrypted256[16] = {0x8e,0xa2,0xb7,0xca,0x51,0x67,0x45,0xbf,
                                       0xea,0xfc,0x49,0x90,0x4b,0x49,0x60,0x89};
    uint8_t key[32], output[16];
    for (unsigned i = 0; i < 32; ++i) key[i] = (uint8_t)i;
    if (!decrypt(encrypted128, 16, key, 16, NULL, 1, output) || memcmp(output, plain, 16) ||
        !decrypt(encrypted256, 16, key, 32, NULL, 1, output) || memcmp(output, plain, 16)) return 1;
    puts("AES-128/256 independent known-vector checks passed.");
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "selftest")) return selftest();
    if (argc != 4) {
        fprintf(stderr, "usage: gm1-literal-key-scan BLOB CIPHERTEXT_64 PLAIN_64 | selftest\n");
        return 2;
    }
    size_t blob_size = 0, cipher_size = 0, plain_size = 0;
    uint8_t *blob = read_file(argv[1], &blob_size);
    uint8_t *cipher = read_file(argv[2], &cipher_size);
    uint8_t *plain = read_file(argv[3], &plain_size);
    if (!blob || !cipher || !plain || blob_size < 16 || cipher_size != 64 || plain_size != 64) {
        fprintf(stderr, "Expected a bounded blob and two 64-byte samples.\n");
        free(blob); free(cipher); free(plain); return 1;
    }
    uint8_t cbc_target[16];
    for (unsigned n = 0; n < 16; ++n) cbc_target[n] = plain[16+n] ^ cipher[n];
    size_t tested[2] = {0}, duplicates[2] = {0}, matches = 0;
    for (size_t offset = 0; offset + 16 <= blob_size; ++offset) {
        for (unsigned kind = 0; kind < 2; ++kind) {
            size_t key_size = kind ? 32 : 16;
            if (offset + key_size > blob_size) continue;
            if (offset && !memcmp(blob + offset, blob + offset - 1, key_size)) {
                ++duplicates[kind]; continue;
            }
            uint8_t block[16], check[64], iv[16] = {0};
            ++tested[kind];
            if (!decrypt(cipher + 16, 16, blob + offset, key_size, NULL, 1, block)) return 1;
            int cbc = !memcmp(block, cbc_target, 16);
            int ecb = !memcmp(block, plain + 16, 16);
            if (!cbc && !ecb) continue;
            if (cbc) {
                if (!decrypt(cipher, 16, blob + offset, key_size, NULL, 1, block)) return 1;
                for (unsigned n = 0; n < 16; ++n) iv[n] = block[n] ^ plain[n];
            }
            if (!decrypt(cipher, 64, blob + offset, key_size, iv, !cbc, check) || memcmp(check, plain, 64)) continue;
            ++matches;
            printf("{\"event\":\"match\",\"offset\":%zu,\"key_bytes\":%zu,\"mode\":\"%s\",\"key_hex\":\"",
                    offset, key_size, cbc ? "cbc" : "ecb");
            hex(blob + offset, key_size);
            printf("\",\"iv_hex\":\""); hex(iv, 16); printf("\"}\n"); fflush(stdout);
        }
        if (offset && offset % (1024 * 1024) == 0) {
            printf("{\"event\":\"progress\",\"offset\":%zu}\n", offset); fflush(stdout);
        }
    }
    printf("{\"event\":\"summary\",\"blob_bytes\":%zu,\"tested_128\":%zu,\"tested_256\":%zu,"
           "\"duplicate_128\":%zu,\"duplicate_256\":%zu,\"matches\":%zu}\n",
           blob_size, tested[0], tested[1], duplicates[0], duplicates[1], matches);
    free(blob); free(cipher); free(plain); return 0;
}
