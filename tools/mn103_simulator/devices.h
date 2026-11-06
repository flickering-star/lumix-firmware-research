/* Optional offline device bindings. GPL-3.0-or-later. */
#ifndef GM5_DEVICES_H
#define GM5_DEVICES_H
#include <stdint.h>
#include <stdio.h>
struct sim_state;
void gm5_devices_nor(struct sim_state *machine, const char *path, uint32_t busy,
                     uint32_t fail_erase, uint32_t fail_program, uint32_t cut_after);
void gm5_devices_log(const char *path);
void gm5_devices_save(const char *path);
void gm5_devices_sync(uint32_t lock_pc, uint32_t unlock_pc, uint32_t identifier);
void gm5_devices_control(struct sim_state *, uint32_t, uint32_t, const char *);
int gm5_devices_control_enabled(void);
void gm5_devices_control_report(FILE *);
int gm5_devices_instruction(uint32_t pc);
void gm5_devices_service_report(FILE *stream);
const char *gm5_devices_stop_reason(void);
void gm5_devices_report(FILE *stream);
void gm5_devices_close(void);
#endif
