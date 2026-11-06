/* Query one standard GetDeviceInfo operation through ImageCaptureCore.
 * Build: clang -fobjc-arc -Wall -Wextra tools/gm5_ptp_info_macos.m \
 *          -framework Foundation -framework ImageCaptureCore -o work/gm5-ptp-info
 * Usage: work/gm5-ptp-info EXISTING_EMPTY_OUTPUT_DIRECTORY
 *
 * Only local USB DMC-GM5 devices with VID 04da/PID 2374 are accepted. No network
 * discovery, vendor commands, settings changes, photo capture/download/delete,
 * raw USB interface claims or firmware operations are implemented. Apple's
 * framework manages its ordinary device/session communication.
 */
#import <Foundation/Foundation.h>
#import <ImageCaptureCore/ImageCaptureCore.h>

@interface GM5InfoProbe : NSObject <ICDeviceBrowserDelegate, ICDeviceDelegate>
@property(strong) ICDeviceBrowser *browser;
@property(strong) ICCameraDevice *camera;
@property(strong) NSURL *directory;
@property(strong) NSMutableDictionary *report;
@property BOOL done;
@property BOOL sent;
@property int status;
@end

@implementation GM5InfoProbe
- (void)finish:(int)status error:(NSString *)message {
    if (self.done) return;
    self.status = status;
    if (message) self.report[@"error"] = message;
    if (self.camera.hasOpenSession) [self.camera requestCloseSession];
    self.done = YES;
}
- (void)deviceBrowser:(ICDeviceBrowser *)browser didAddDevice:(ICDevice *)device moreComing:(BOOL)more {
    (void)browser; (void)more;
    if (self.camera || ![device isKindOfClass:[ICCameraDevice class]] ||
        ![device.transportType isEqualToString:ICTransportTypeUSB] ||
        device.usbVendorID != 0x04da || device.usbProductID != 0x2374 ||
        !device.name ||
        [device.name rangeOfString:@"DMC-GM5"].location == NSNotFound) return;
    self.camera = (ICCameraDevice *)device;
    self.report[@"name"] = device.name ?: @"";
    self.report[@"vendor_id"] = @(device.usbVendorID);
    self.report[@"product_id"] = @(device.usbProductID);
    self.report[@"capabilities"] = device.capabilities;
    if (![device.capabilities containsObject:ICCameraDeviceCanAcceptPTPCommands]) {
        [self finish:1 error:@"ImageCaptureCore does not advertise PTP pass-through"];
        return;
    }
    device.delegate = self;
    [device requestOpenSession];
}
- (void)deviceBrowser:(ICDeviceBrowser *)browser didRemoveDevice:(ICDevice *)device moreGoing:(BOOL)more {
    (void)browser; (void)more;
    if (device == self.camera) [self finish:1 error:@"Camera disconnected"];
}
- (void)didRemoveDevice:(ICDevice *)device {
    if (device == self.camera) [self finish:1 error:@"Camera disconnected"];
}
- (void)device:(ICDevice *)device didOpenSessionWithError:(NSError *)error {
    (void)device;
    if (error) { [self finish:1 error:error.localizedDescription]; return; }
    if (self.sent) return;
    self.sent = YES;
    /* USB PTP command container: length 12, type command, GetDeviceInfo, tx 1. */
    const uint8_t bytes[] = {12,0,0,0, 1,0, 1,0x10, 1,0,0,0};
    NSData *command = [NSData dataWithBytes:bytes length:sizeof(bytes)];
    NSError *writeError = nil;
    if (![command writeToURL:[self.directory URLByAppendingPathComponent:@"get-device-info-command.bin"]
                    options:NSDataWritingWithoutOverwriting error:&writeError]) {
        [self finish:1 error:writeError.localizedDescription]; return;
    }
    self.report[@"explicit_operation"] = @"0x1001 GetDeviceInfo";
    [self.camera requestSendPTPCommand:command outData:nil sendCommandDelegate:self
        didSendCommandSelector:@selector(didSendPTPCommand:inData:response:error:contextInfo:)
        contextInfo:NULL];
}
- (void)didSendPTPCommand:(NSData *)command inData:(NSData *)data response:(NSData *)response
                   error:(NSError *)error contextInfo:(void *)context {
    (void)command; (void)context;
    self.report[@"data_bytes"] = @(data.length);
    self.report[@"response_bytes"] = @(response.length);
    NSError *writeError = nil;
    if (data && ![data writeToURL:[self.directory URLByAppendingPathComponent:@"get-device-info-data.bin"]
                         options:NSDataWritingWithoutOverwriting error:&writeError]) {
        [self finish:1 error:writeError.localizedDescription]; return;
    }
    if (response && ![response writeToURL:[self.directory URLByAppendingPathComponent:@"get-device-info-response.bin"]
                                 options:NSDataWritingWithoutOverwriting error:&writeError]) {
        [self finish:1 error:writeError.localizedDescription]; return;
    }
    if (!error) {
        const uint8_t *raw = response.bytes;
        if (response.length != 12 || raw[4] != 3 || raw[5] != 0 ||
            raw[6] != 1 || raw[7] != 0x20) {
            [self finish:1 error:@"GetDeviceInfo returned a non-OK or malformed PTP response"];
            return;
        }
    }
    [self finish:error ? 1 : 0 error:error.localizedDescription];
}
- (void)device:(ICDevice *)device didCloseSessionWithError:(NSError *)error {
    (void)device;
    self.report[@"session_closed"] = @YES;
    if (error) self.report[@"close_error"] = error.localizedDescription;
}
@end

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc != 2) { fprintf(stderr, "usage: gm5-ptp-info EXISTING_EMPTY_OUTPUT_DIRECTORY\n"); return 2; }
        NSString *path = [NSString stringWithUTF8String:argv[1]];
        NSError *error = nil;
        NSArray *contents = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:&error];
        if (!contents || contents.count != 0) {
            fprintf(stderr, "Output directory must exist and be empty\n"); return 2;
        }
        GM5InfoProbe *probe = [GM5InfoProbe new];
        probe.directory = [NSURL fileURLWithPath:path isDirectory:YES];
        probe.report = [@{@"transport":@"USB", @"local_devices_only":@YES,
                          @"framework":@"ImageCaptureCore", @"vendor_commands_sent":@NO} mutableCopy];
        probe.browser = [ICDeviceBrowser new];
        probe.browser.browsedDeviceTypeMask = (ICDeviceTypeMask)(ICDeviceTypeMaskCamera | ICDeviceLocationTypeMaskLocal);
        probe.browser.delegate = probe;
        [probe.browser start];
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:35];
        while (!probe.done && deadline.timeIntervalSinceNow > 0)
            [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        if (!probe.done) [probe finish:1 error:@"Timed out waiting for GM5 or GetDeviceInfo"];
        /* Allow the framework's asynchronous session close to finish. */
        NSDate *closeDeadline = [NSDate dateWithTimeIntervalSinceNow:2];
        while (probe.camera.hasOpenSession && closeDeadline.timeIntervalSinceNow > 0)
            [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        [probe.browser stop];
        NSData *json = [NSJSONSerialization dataWithJSONObject:probe.report options:NSJSONWritingPrettyPrinted error:&error];
        if (!json || ![json writeToURL:[probe.directory URLByAppendingPathComponent:@"probe-result.json"]
                               options:NSDataWritingWithoutOverwriting error:&error]) {
            fprintf(stderr, "Could not save result\n"); return 1;
        }
        fwrite(json.bytes, 1, json.length, stdout); putchar('\n');
        return probe.status;
    }
}
