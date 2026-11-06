/* Read-only adapter for unmodified GNU binutils 2.42 MN10300 decoder sources.
 * This host utility disassembles bytes; it never executes camera instructions.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdarg.h>
#include "disassemble.h"
int print_insn_mn10300(bfd_vma, struct disassemble_info *);
static unsigned char *data;
static size_t size;
static bfd_vma base;
static int emit(void *stream, const char *format, ...) {
  va_list args; va_start(args,format); int n=vfprintf(stream,format,args); va_end(args); return n;
}
static int read_bytes(bfd_vma at, bfd_byte *out, unsigned int n, struct disassemble_info *info) {
  (void)info;
  if (at<base || at-base>size || n>size-(at-base)) return 1;
  memcpy(out,data+(at-base),n); return 0;
}
static void memory_error(int status,bfd_vma at,struct disassemble_info *info) {
  (void)status;(void)info;fprintf(stderr,"memory outside supplied file at 0x%llx\n",(unsigned long long)at);
}
static void address(bfd_vma at,struct disassemble_info *info) {
  emit(info->stream,"0x%08x",(unsigned int)at);
}
int main(int argc,char **argv) {
  if (argc!=6) {fprintf(stderr,"usage: mn103-dis FILE BASE START END MACH\n");return 2;}
  FILE *input=fopen(argv[1],"rb");if(!input)return 2;
  fseek(input,0,SEEK_END);long length=ftell(input);rewind(input);
  if(length<=0 || length>64*1024*1024){fclose(input);return 2;}
  size=(size_t)length;data=malloc(size);if(!data){fclose(input);return 2;}
  if(fread(data,1,size,input)!=size){fclose(input);free(data);return 2;}fclose(input);
  base=strtoull(argv[2],NULL,0);bfd_vma start=strtoull(argv[3],NULL,0),end=strtoull(argv[4],NULL,0);
  if(start<base || start>end || end-base>size){free(data);return 2;}
  struct disassemble_info info={0};info.mach=strtoul(argv[5],NULL,0);info.stream=stdout;
  info.fprintf_func=emit;info.read_memory_func=read_bytes;info.memory_error_func=memory_error;info.print_address_func=address;
  for(bfd_vma at=start;at<end;){
    printf("%08x  ",(unsigned int)at);
    int consumed=print_insn_mn10300(at,&info);if(consumed<=0){free(data);return 1;}
    printf("\t; ");for(int i=0;i<consumed && at+i<base+size;i++)printf("%02x",data[at-base+i]);puts("");at+=consumed;
  }
  free(data);return 0;
}
