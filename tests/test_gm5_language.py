"""Test the actual one-word English setter through a fake USB interface."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "captures/gm5-usb-usb-handler-NhRSm6fb/result/usb-handler.bin"

HARNESS = r'''
static unsigned phase, operation, address, writes;
static uint8_t handler[1024], absolute_handler[1024], settings[UPDATE_BYTES], ui_state[1024];
static const char *scenario;
static IOReturn fake_control(void *self, UInt8 pipe, IOUSBDevRequestTO *request) {
    (void)self;
    if (pipe || request->bmRequestType != 0x40 || request->bRequest || request->wValue || request->wLength)
        return kIOReturnBadArgument;
    if (!request->wIndex && phase == 0) phase = 1;
    else if (request->wIndex == 1 && phase == 2) phase = 3;
    else if (request->wIndex == 1 && phase == 4) phase = 5;
    else return kIOReturnBadArgument;
    return 0;
}
static IOReturn fake_send(void *self, UInt8 pipe, void *buffer, UInt32 length, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *packet = buffer;
    if (pipe != 1 || phase != 1) return kIOReturnBadArgument;
    operation = packet[3];
    address = (unsigned)packet[4] | (unsigned)packet[5]<<8 | (unsigned)packet[6]<<16 | (unsigned)packet[7]<<24;
    if (operation == 0x34) {
        uint8_t expected[16]; language_request(expected);
        if (length != 16 || memcmp(packet,expected,16) || writes) return kIOReturnBadArgument;
        writes++;
        if (strcmp(scenario,"write_ignored")) settings[LANGUAGE_OFFSET+1] = 1;
    } else if (operation == 0x9c) {
        uint8_t expected[16]; ui_language_request(expected);
        if (length != 16 || memcmp(packet,expected,16) || writes != 1) return kIOReturnBadArgument;
        writes++; ui_state[0x239] = 1;
    } else if (operation != 0x5c || length != BLOCK_FRAME_BYTES) return kIOReturnBadArgument;
    phase = 2; return 0;
}
static IOReturn fake_receive(void *self, UInt8 pipe, void *buffer, UInt32 *length, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *packet = buffer;
    unsigned type = operation == 0x34 || operation == 0x9c ? 8 : 1;
    if (pipe != 2) return kIOReturnBadArgument;
    if (phase == 3 && *length == 1) { packet[0] = (uint8_t)type; phase = 4; return 0; }
    if (phase != 5 || *length != (type == 8 ? 16 : BLOCK_FRAME_BYTES)) return kIOReturnBadArgument;
    memset(packet,0,*length); packet[0] = (uint8_t)type; packet[2] = 255; packet[3] = type == 8 ? 1 : 5;
    if (type == 1) {
        uint8_t *data = packet+4;
        if (address == 0x4061e400) {
            memcpy(data+0x164,"\x65\xcd\x36\x40",4); memcpy(data+0x304,"\x71\xce\x36\x40",4);
        } else if (address == 0x4036cc00) {
            memcpy(data+0x165,"\xcd\x22\x08\xf0\x14\xdf\x00\x04",8);
            memcpy(data+0x271,"\xcd\x15\x12\xf0\x18\xdf\x00\x04",8);
        }
        else if (address == 0x4036d400) {
            memcpy(data,handler,1024);
            if (!strcmp(scenario,"handler_changed")) data[0x187] ^= 1;
        } else if (address == 0x4036e000) memcpy(data,absolute_handler,1024);
        else if (address == 0x701af000) memcpy(data,ui_state,1024);
        else if (address == 0x70a0f000) { data[0x150] = 1; data[0x152] = 4; data[0x158] = 255; data[0x159] = 255;
        } else if (address == 0x70a67800 || address == 0x702ff800) {
        } else if (address >= 0x7bfb0000 && address < 0x7bfb4800) memcpy(data,settings+address-0x7bfb0000,1024);
        else return kIOReturnBadArgument;
    }
    packet[*length-2] = frame_checksum(packet,*length); phase = 0; return 0;
}
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    scenario = argv[3];
    FILE *file = fopen(argv[2],"rb");
    if (!file || fseek(file,0x1400,SEEK_SET) || fread(handler,1,1024,file) != 1024) return 1;
    if (fseek(file,0x2000,SEEK_SET) || fread(absolute_handler,1,1024,file) != 1024) return 1;
    fclose(file);
    for (unsigned n = 0; n < UPDATE_BYTES; n++) settings[n] = (uint8_t)(n*7/11);
    const uint8_t japanese[12] = {0,0,0,0,0x0f,0x27,0x63,0x63,0x0f,0x27,0x63,0x63};
    memcpy(settings+LANGUAGE_OFFSET,japanese,12);
    if (!strcmp(scenario,"pattern_changed")) settings[LANGUAGE_OFFSET] = 1;
    events = tmpfile(); if (!events) return 1;
    IOUSBInterfaceInterface300 methods = {0};
    methods.ControlRequestTO = fake_control; methods.WritePipeTO = fake_send; methods.ReadPipeTO = fake_receive;
    IOUSBInterfaceInterface300 *pointer = &methods;
    bool result = probe_custom_action(&pointer,1,2,argv[1]); fclose(events);
    if (!strcmp(scenario,"success")) return result && writes == 2 && ui_english_readback && readback_differences == 1 && settings[LANGUAGE_OFFSET+1] == 1 ? 0 : 1;
    if (!strcmp(scenario,"write_ignored")) return !result && writes == 2 && !english_readback ? 0 : 1;
    return !result && !writes && !language_write_attempts ? 0 : 1;
}
'''


@unittest.skipUnless(sys.platform == "darwin" and FIXTURE.exists(),
                     "Requires macOS SDK and retained GM5 settings-writer fixture")
class LanguageTests(unittest.TestCase):
    def test_single_word_write_guards_and_readback_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.c"
            code = (ROOT / "tools/gm5_language_macos.c").read_text()
            code = code.replace('#include "gm1_usb_probe_macos.c"',
                                '#include '+json.dumps(str(ROOT / "tools/gm1_usb_probe_macos.c")))
            code = code.replace("int main(int argc, char **argv)", "int original_language_main(int argc, char **argv)")
            source.write_text(code+"\n"+HARNESS)
            binary = root / "test"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-deprecated-declarations",
                            "-fsanitize=address,undefined", str(source), "-framework", "IOKit",
                            "-framework", "CoreFoundation", "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            for scenario in ("success", "handler_changed", "pattern_changed", "write_ignored"):
                with self.subTest(scenario=scenario):
                    output = root / scenario
                    output.mkdir()
                    subprocess.run([str(binary), str(output), str(FIXTURE), scenario],
                                   check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
