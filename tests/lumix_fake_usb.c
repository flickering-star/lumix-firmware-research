/* Native ABI/transport test peer. It opens no operating-system USB device.
 * Layout declarations model the public libusb descriptor ABI. All transfer
 * replies and fault modes below are explicit fixtures, not camera behavior. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

struct device_descriptor {
    uint8_t length,type; uint16_t usb; uint8_t cls,sub,protocol,packet0;
    uint16_t vid,pid,release; uint8_t manufacturer,product,serial,configurations;
};
struct endpoint_descriptor {
    uint8_t length,type,address,attributes; uint16_t packet;
    uint8_t interval,refresh,synch; const unsigned char *extra; int extra_length;
};
struct alternate_descriptor {
    uint8_t length,type,number,alternate,count,cls,sub,protocol,string;
    const struct endpoint_descriptor *endpoint; const unsigned char *extra; int extra_length;
};
struct interface_descriptor {const struct alternate_descriptor *alternate; int count;};
struct configuration_descriptor {
    uint8_t length,type; uint16_t total; uint8_t count,value,string,attributes,power;
    const struct interface_descriptor *interface; const unsigned char *extra; int extra_length;
};

enum {INIT,LIST,DESC,CONFIG,FREE_CONFIG,OPEN,CLAIM,CONTROL,BULK,RELEASE,CLOSE,FREE_LIST,EXIT,INVALID,COUNTERS};
static unsigned calls[COUNTERS];
static int fault,phase,kind,packet_size;
static uint32_t address;
static unsigned char context_tag,device_tag,handle_tag;
static void *devices[3];
static struct endpoint_descriptor endpoints[3];
static struct alternate_descriptor alternate;
static struct interface_descriptor interface;
static struct configuration_descriptor configuration;

static int bad(void) {calls[INVALID]++;return -2;}
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static unsigned char checksum(const unsigned char *p,int n) {
    unsigned value=0;for(int i=1;i<n-2;i++)value+=p[i];return (unsigned char)value;
}

API void lumix_fake_case(int value) {
    memset(calls,0,sizeof calls);fault=value;phase=kind=packet_size=0;address=0;
    memset(endpoints,0,sizeof endpoints);memset(&alternate,0,sizeof alternate);
    memset(&interface,0,sizeof interface);memset(&configuration,0,sizeof configuration);
    devices[0]=&device_tag;devices[1]=&device_tag;devices[2]=NULL;
    for(int i=0;i<3;i++){endpoints[i].length=7;endpoints[i].type=5;endpoints[i].packet=64;}
    endpoints[0].address=1;endpoints[0].attributes=2;
    endpoints[1].address=0x82;endpoints[1].attributes=2;
    endpoints[2].address=fault==3?0x84:0x83;endpoints[2].attributes=3;
    alternate.length=9;alternate.type=4;alternate.count=3;
    alternate.cls=255;alternate.sub=160;alternate.protocol=176;alternate.endpoint=endpoints;
    interface.alternate=&alternate;interface.count=1;
    configuration.length=9;configuration.type=2;configuration.total=39;
    configuration.count=1;configuration.value=1;configuration.interface=&interface;
}
API unsigned lumix_fake_count(int index) {return index>=0&&index<COUNTERS?calls[index]:~0u;}
API size_t lumix_fake_layout(int index) {
    const size_t values[]={sizeof(struct device_descriptor),sizeof(struct endpoint_descriptor),
        sizeof(struct alternate_descriptor),sizeof(struct interface_descriptor),sizeof(struct configuration_descriptor),
        offsetof(struct endpoint_descriptor,extra),offsetof(struct alternate_descriptor,endpoint),
        offsetof(struct configuration_descriptor,interface)};
    return index>=0&&index<8?values[index]:0;
}
API int libusb_init(void **context) {
    calls[INIT]++;if(!context)return bad();*context=&context_tag;return 0;
}
API ptrdiff_t libusb_get_device_list(void *context,void ***list) {
    calls[LIST]++;if(context!=&context_tag||!list)return bad();*list=devices;
    return fault==9?0:fault==1?2:1;
}
API int libusb_get_device_descriptor(void *device,struct device_descriptor *d) {
    calls[DESC]++;if(device!=&device_tag||!d)return bad();memset(d,0,sizeof *d);
    d->length=18;d->type=1;d->usb=0x200;d->packet0=64;d->vid=0x04da;d->pid=0x2370;
    d->release=0x100;d->product=1;d->serial=2;d->configurations=1;return 0;
}
API int libusb_get_config_descriptor(void *device,uint8_t index,struct configuration_descriptor **out) {
    calls[CONFIG]++;if(device!=&device_tag||index||!out)return bad();*out=&configuration;return 0;
}
API void libusb_free_config_descriptor(struct configuration_descriptor *d) {
    calls[FREE_CONFIG]++;if(d!=&configuration)(void)bad();
}
API int libusb_open(void *device,void **out) {
    calls[OPEN]++;if(device!=&device_tag||!out)return bad();*out=&handle_tag;return 0;
}
API int libusb_get_string_descriptor_ascii(void *handle,uint8_t index,unsigned char *data,int size) {
    if(handle!=&handle_tag||!data||size<32||(index!=1&&index!=2))return bad();
    const char *text=index==2?"fixture-camera":fault==2?"DC-GX7MK3":"DMC-GM5";
    size_t n=strlen(text);memcpy(data,text,n);return (int)n;
}
API int libusb_get_configuration(void *handle,int *value) {
    if(handle!=&handle_tag||!value)return bad();*value=fault==10?2:1;return 0;
}
API int libusb_claim_interface(void *handle,int number) {
    calls[CLAIM]++;if(handle!=&handle_tag||number)return bad();return fault==4?-6:fault==11?-12:0;
}
API int libusb_control_transfer(void *handle,uint8_t type,uint8_t request,uint16_t value,
                                uint16_t index,unsigned char *data,uint16_t length,unsigned timeout) {
    calls[CONTROL]++;
    if(handle!=&handle_tag||type!=0x40||request||value||data||length||timeout!=1500)return bad();
    if(fault==8)return -4;
    if((phase==0&&index==0)||(phase==2&&index==1)||(phase==4&&index==1)){phase++;return 0;}
    return bad();
}
API int libusb_bulk_transfer(void *handle,uint8_t endpoint,unsigned char *data,int size,int *actual,unsigned timeout) {
    calls[BULK]++;if(handle!=&handle_tag||!data||!actual||timeout!=1500)return bad();
    if(fault==6&&phase==1)return -7;
    if(phase==1&&endpoint==1) {
        if((size!=1030&&size!=16)||data[1]||data[2]!=255||data[size-1]||data[size-2]!=checksum(data,size))return bad();
        kind=data[0];packet_size=size;
        if(kind==1&&size==1030&&data[3]==0x5c){address=le32(data+4);if(le32(data+8)!=address+1024)return bad();}
        else if(kind==8&&size==16&&data[3]==0x9c) {
            if(le32(data+4)!=0x70a68490||data[8]||data[9])return bad();
            for(int i=10;i<14;i++)if(data[i])return bad();
        } else return bad();
        *actual=size;phase=2;return 0;
    }
    if(phase==3&&endpoint==0x82&&size==1){data[0]=(unsigned char)(fault==7?99:kind);*actual=1;phase=4;return 0;}
    if(phase==5&&endpoint==0x82&&size==packet_size) {
        memset(data,0,(size_t)size);data[0]=(unsigned char)kind;data[2]=255;data[3]=(unsigned char)(kind==1?5:1);
        if(kind==1)for(int i=0;i<1024;i++)data[4+i]=(unsigned char)(address+(unsigned)i);
        data[size-2]=checksum(data,size);*actual=fault==5?size-1:size;phase=0;return 0;
    }
    return bad();
}
API int libusb_release_interface(void *handle,int number) {
    calls[RELEASE]++;if(handle!=&handle_tag||number)return bad();return 0;
}
API void libusb_close(void *handle) {calls[CLOSE]++;if(handle!=&handle_tag)(void)bad();}
API void libusb_free_device_list(void **list,int unref) {calls[FREE_LIST]++;if(list!=devices||unref!=1)(void)bad();}
API void libusb_exit(void *context) {calls[EXIT]++;if(context!=&context_tag)(void)bad();}
