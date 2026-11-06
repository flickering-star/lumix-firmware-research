#include <stdint.h>
typedef uint64_t bfd_vma;
typedef unsigned char bfd_byte;
struct disassemble_info {
  unsigned long mach;
  void *stream;
  int (*fprintf_func)(void *, const char *, ...);
  int (*read_memory_func)(bfd_vma, bfd_byte *, unsigned int, struct disassemble_info *);
  void (*memory_error_func)(int, bfd_vma, struct disassemble_info *);
  void (*print_address_func)(bfd_vma, struct disassemble_info *);
};
static inline unsigned long bfd_getl16(const bfd_byte *p) { return p[0] | (unsigned long)p[1]<<8; }
static inline unsigned long bfd_getl32(const bfd_byte *p) { return bfd_getl16(p) | bfd_getl16(p+2)<<16; }
static inline unsigned long bfd_getb16(const bfd_byte *p) { return p[1] | (unsigned long)p[0]<<8; }
static inline unsigned long bfd_getb32(const bfd_byte *p) { return bfd_getb16(p+2) | bfd_getb16(p)<<16; }
