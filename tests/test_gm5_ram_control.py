"""Exercise the fixed GM5 RAM toggle/restore with fake USB, never a device."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "captures/gm5-usb-usb-handler-NhRSm6fb/result/usb-handler.bin"

HARNESS = r'''
static unsigned phase, operation, address, writes, ram_value = 1;
static unsigned values[2];
static uint8_t installed_handler[1024];
static const char *scenario;
static IOReturn control(void *self, UInt8 pipe, IOUSBDevRequestTO *request) {
    (void)self;
    if (pipe || request->bmRequestType != 0x40 || request->bRequest || request->wValue || request->wLength)
        return kIOReturnBadArgument;
    if (!request->wIndex && phase == 0) phase = 1;
    else if (request->wIndex == 1 && phase == 2) phase = 3;
    else if (request->wIndex == 1 && phase == 4) phase = 5;
    else return kIOReturnBadArgument;
    return 0;
}
static IOReturn send(void *self, UInt8 pipe, void *buffer, UInt32 length, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *packet = buffer;
    if (pipe != 1 || phase != 1) return kIOReturnBadArgument;
    operation = packet[3];
    address = (unsigned)packet[4] | (unsigned)packet[5]<<8 | (unsigned)packet[6]<<16 | (unsigned)packet[7]<<24;
    if (operation == 0x9c) {
        uint8_t expected[16];
        if (length != 16 || !ram_request(expected,packet[8]) || memcmp(packet,expected,16) || writes >= 2)
            return kIOReturnBadArgument;
        values[writes++] = packet[8]; ram_value = packet[8];
    } else if (operation != 0x5c || length != BLOCK_FRAME_BYTES) return kIOReturnBadArgument;
    phase = 2;
    return 0;
}
static IOReturn receive(void *self, UInt8 pipe, void *buffer, UInt32 *length, UInt32 idle, UInt32 total) {
    (void)self; (void)idle; (void)total;
    uint8_t *packet = buffer;
    unsigned type = operation == 0x9c ? 8 : 1;
    if (pipe != 2) return kIOReturnBadArgument;
    if (phase == 3 && *length == 1) { packet[0] = (uint8_t)type; phase = 4; return 0; }
    if (phase != 5 || *length != (type == 8 ? 16 : BLOCK_FRAME_BYTES)) return kIOReturnBadArgument;
    memset(packet,0,*length); packet[0] = (uint8_t)type; packet[2] = 255;
    packet[3] = type == 8 ? 1 : 5;
    if (type == 1) {
        uint8_t *data = packet+4;
        if (address == 0x4061e400) memcpy(data+0x304,"\x71\xce\x36\x40",4);
        else if (address == 0x4036cc00) memcpy(data+0x271,"\xcd\x15\x12\xf0\x18\xdf\x00\x04",8);
        else if (address == 0x4036e000) {
            memcpy(data,installed_handler,1024);
            if (!strcmp(scenario,"handler_changed")) data[0x86] ^= 1;
        } else if (address == 0x702ff800) {
            if (!strcmp(scenario,"wrong_usb_mode")) data[0x5d] = 1;
        } else if (address == 0x70a68400) {
            data[0x90] = (uint8_t)ram_value;
            if (!strcmp(scenario,"wrong_readback") && writes == 1) data[0x90] = 2;
        } else return kIOReturnBadArgument;
    }
    packet[*length-2] = frame_checksum(packet,*length);
    if (type == 8 && writes == 1 && !strcmp(scenario,"bad_clear_ack")) packet[*length-2] ^= 1;
    phase = 0;
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    scenario = argv[3];
    FILE *fixture = fopen(argv[2],"rb");
    if (!fixture || fseek(fixture,0x2000,SEEK_SET) || fread(installed_handler,1,1024,fixture) != 1024)
        return 1;
    fclose(fixture);
    if (!strcmp(scenario,"wrong_initial_value")) ram_value = 2;
    if (!strcmp(scenario,"enable")) ram_action = RAM_ENABLE;
    if (!strcmp(scenario,"restore") || !strcmp(scenario,"restore_already_one")) {
        ram_action = RAM_RESTORE;
        ram_value = !strcmp(scenario,"restore") ? 0 : 1;
    }
    events = tmpfile(); if (!events) return 1;
    IOUSBInterfaceInterface300 methods = {0};
    methods.ControlRequestTO = control; methods.WritePipeTO = send; methods.ReadPipeTO = receive;
    IOUSBInterfaceInterface300 *pointer = &methods;
    bool result = gm5_ram_toggle_test(&pointer,1,2,argv[1]);
    fclose(events);
    if (!strcmp(scenario,"enable")) return result && !ram_restore_verified && ram_value == 0 && writes == 1 && values[0] == 0 ? 0 : 1;
    if (!strcmp(scenario,"restore")) return result && ram_restore_verified && ram_value == 1 && writes == 1 && values[0] == 1 ? 0 : 1;
    if (!strcmp(scenario,"restore_already_one")) return result && ram_restore_verified && ram_value == 1 && !writes ? 0 : 1;
    bool before_write_failure = !strcmp(scenario,"handler_changed")
        || !strcmp(scenario,"wrong_usb_mode") || !strcmp(scenario,"wrong_initial_value");
    if (before_write_failure) return !result && writes == 0 && !ram_write_attempts ? 0 : 1;
    bool expected_result = !strcmp(scenario,"success");
    return result == expected_result && ram_restore_verified && ram_value == 1
        && writes == 2 && values[0] == 0 && values[1] == 1 && !phase ? 0 : 1;
}
'''


@unittest.skipUnless(sys.platform == "darwin" and FIXTURE.exists(),
                     "Requires macOS SDK and retained physical GM5 handler fixture")
class RamControlTests(unittest.TestCase):
    def test_guards_readbacks_and_cleanup_restore_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.c"
            # Rename only the CLI entry; exercise the unchanged actual RAM code.
            tool_copy = (ROOT / "tools/gm5_ram_control_macos.c").read_text()
            tool_copy = tool_copy.replace('#include "gm1_usb_probe_macos.c"',
                                          '#include '+json.dumps(str(ROOT / "tools/gm1_usb_probe_macos.c")))
            tool_copy = tool_copy.replace("int main(int argc, char **argv)", "int actual_ram_tool_main(int argc, char **argv)")
            source.write_text(tool_copy+"\n"+HARNESS)
            binary = root / "test"
            subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-deprecated-declarations", "-fsanitize=address,undefined", str(source),
                            "-framework", "IOKit", "-framework", "CoreFoundation", "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            for scenario in ("success", "bad_clear_ack", "wrong_readback", "handler_changed",
                             "wrong_usb_mode", "wrong_initial_value", "enable", "restore", "restore_already_one"):
                with self.subTest(scenario=scenario):
                    output = root / scenario
                    output.mkdir()
                    subprocess.run([str(binary), str(output), str(FIXTURE), scenario],
                                   check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
