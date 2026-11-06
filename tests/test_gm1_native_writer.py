"""Exercise actual native file/resume code through a fake USB interface."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HARNESS = r'''
static unsigned fake_phase, fake_index, observed[32], observed_count;
static void sample(unsigned index, uint8_t data[BLOCK_BYTES]) {
    for (unsigned n = 0; n < BLOCK_BYTES; ++n) data[n] = (uint8_t)(index * 7 + n / 8);
}
static IOReturn fake_control(void *self, UInt8 pipe, IOUSBDevRequestTO *req) {
    (void)self;
    if (pipe || req->bmRequestType != 0x40 || req->bRequest || req->wValue || req->wLength)
        return kIOReturnBadArgument;
    if (!req->wIndex && !fake_phase) fake_phase = 1;
    else if (req->wIndex == 1 && fake_phase == 2) fake_phase = 3;
    else if (req->wIndex == 1 && fake_phase == 4) fake_phase = 5;
    else return kIOReturnBadArgument;
    return 0;
}
static IOReturn fake_write(void *self, UInt8 pipe, void *buffer, UInt32 size, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *p = buffer;
    if (fake_phase != 1 || pipe != 1 || size != BLOCK_FRAME_BYTES || p[0] != 1 || p[3] != 0x5c)
        return kIOReturnBadArgument;
    uint32_t start = (uint32_t)p[4] | (uint32_t)p[5] << 8 | (uint32_t)p[6] << 16 | (uint32_t)p[7] << 24;
    fake_index = (start - 0x40000000) / BLOCK_BYTES;
    if (observed_count >= 32) return kIOReturnBadArgument;
    observed[observed_count++] = fake_index;
    fake_phase = 2;
    return 0;
}
static IOReturn fake_read(void *self, UInt8 pipe, void *buffer, UInt32 *size, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *p = buffer;
    if (pipe != 2) return kIOReturnBadArgument;
    if (fake_phase == 3 && *size == 1) {
        p[0] = 1; fake_phase = 4; return 0;
    }
    if (fake_phase != 5 || *size != BLOCK_FRAME_BYTES) return kIOReturnBadArgument;
    memset(p, 0, *size); p[0] = 1; p[2] = 255; p[3] = 5;
    sample(fake_index, p + 4);
    p[*size - 2] = frame_checksum(p, *size);
    fake_phase = 0;
    return 0;
}
static bool verify_file(const char *directory, const char *name, unsigned base, unsigned count) {
    char path[4096]; snprintf(path, sizeof path, "%s/%s", directory, name);
    FILE *file = fopen(path, "rb");
    if (!file) return false;
    bool ok = true;
    for (unsigned n = 0; n < count; ++n) {
        uint8_t actual[BLOCK_BYTES], expected[BLOCK_BYTES]; sample(base + n, expected);
        if (fread(actual, 1, sizeof actual, file) != sizeof actual || memcmp(actual, expected, sizeof actual)) {
            ok = false; break;
        }
    }
    if (fgetc(file) != EOF || ferror(file)) ok = false;
    fclose(file); return ok;
}
static bool test_resume(IOUSBInterfaceInterface300 **usb, const char *directory, unsigned base, const char *name) {
    char path[4096]; snprintf(path, sizeof path, "%s/%s-prefix", directory, name);
    FILE *prefix = fopen(path, "wx"); if (!prefix) return false;
    for (unsigned n = 0; n < 3; ++n) {
        uint8_t data[BLOCK_BYTES]; sample(base + n, data);
        if (fwrite(data, 1, sizeof data, prefix) != sizeof data) { fclose(prefix); return false; }
    }
    if (fclose(prefix)) return false;
    resume_input_bytes = 3 * BLOCK_BYTES;
    copied_prefix_bytes = resume_anchor_blocks = 0;
    unsigned first_observation = observed_count;
    if (!read_program_blocks(usb, 1, 2, directory, name, base, base + 3, 2, false, NULL, path)) return false;
    if (resume_anchor_blocks != 3 || copied_prefix_bytes != 3 * BLOCK_BYTES ||
        !verify_file(directory, name, base, 5)) return false;
    for (unsigned n = 0; n < 5; ++n)
        if (observed[first_observation + n] != base + n) return false;
    char prefix_name[128]; snprintf(prefix_name, sizeof prefix_name, "%s-prefix", name);
    return verify_file(directory, prefix_name, base, 3);
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    events = tmpfile(); if (!events) return 1;
    IOUSBInterfaceInterface300 vtable = {0};
    vtable.ControlRequestTO = fake_control;
    vtable.WritePipeTO = fake_write;
    vtable.ReadPipeTO = fake_read;
    IOUSBInterfaceInterface300 *pointer = &vtable;
    IOUSBInterfaceInterface300 **usb = &pointer;
    unsigned init_base = 0x5a3800 / BLOCK_BYTES;
    bool ok = read_program_blocks(usb, 1, 2, argv[1], "initializer.bin", init_base, init_base, 2, false, NULL, NULL)
        && verify_file(argv[1], "initializer.bin", init_base, 2)
        && read_program_blocks(usb, 1, 2, argv[1], "secondary.bin", SECONDARY_FIRST_BLOCK, SECONDARY_FIRST_BLOCK, 2, false, NULL, NULL)
        && verify_file(argv[1], "secondary.bin", SECONDARY_FIRST_BLOCK, 2)
        && test_resume(usb, argv[1], SECONDARY_FIRST_BLOCK, "secondary-resumed.bin")
        && test_resume(usb, argv[1], 0, "main-resumed.bin");
    fclose(events);
    return ok && !fake_phase ? 0 : 1;
}
'''


@unittest.skipUnless(sys.platform == "darwin", "Native IOUSBLib code requires the macOS SDK")
class NativeWriterTests(unittest.TestCase):
    def test_dense_windows_and_resumed_main_and_secondary_files(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "writer-test.c"
            source.write_text("#define main gm1_original_main\n#include "
                              + json.dumps(str(root / "tools/gm1_usb_probe_macos.c"))
                              + "\n#undef main\n" + HARNESS)
            binary = directory / "writer-test"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-deprecated-declarations", "-fsanitize=address,undefined",
                            str(source), "-framework", "IOKit", "-framework", "CoreFoundation",
                            "-o", str(binary)], check=True, capture_output=True, text=True)
            output = subprocess.run([str(binary), str(directory)], check=True, capture_output=True, text=True)
            self.assertEqual(output.stdout.count("Resume anchors match"), 2)
            self.assertEqual((directory / "initializer.bin").stat().st_size, 2048)
            self.assertEqual((directory / "secondary.bin").stat().st_size, 2048)
            self.assertEqual((directory / "secondary-resumed.bin").stat().st_size, 5120)
            self.assertEqual((directory / "main-resumed.bin").stat().st_size, 5120)


if __name__ == "__main__":
    unittest.main()
