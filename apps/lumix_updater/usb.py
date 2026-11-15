"""Portable libusb transport; no driver installation, reset or auto-retry."""
from __future__ import annotations
import ctypes as C
from pathlib import Path
import sys
import time

U8,U16=C.c_uint8,C.c_uint16


class USBError(RuntimeError):
    pass


class Device(C.Structure):
    _fields_=[('length',U8),('type',U8),('usb',U16),('cls',U8),('sub',U8),('protocol',U8),
        ('packet0',U8),('vid',U16),('pid',U16),('release',U16),('manufacturer',U8),
        ('product',U8),('serial',U8),('configurations',U8)]


class Endpoint(C.Structure):
    _fields_=[('length',U8),('type',U8),('address',U8),('attributes',U8),('packet',U16),
        ('interval',U8),('refresh',U8),('synch',U8),('extra',C.c_void_p),('extra_length',C.c_int)]


class Alternate(C.Structure):
    _fields_=[('length',U8),('type',U8),('number',U8),('alternate',U8),('count',U8),
        ('cls',U8),('sub',U8),('protocol',U8),('string',U8),('endpoint',C.POINTER(Endpoint)),
        ('extra',C.c_void_p),('extra_length',C.c_int)]


class Interface(C.Structure):
    _fields_=[('alternate',C.POINTER(Alternate)),('count',C.c_int)]


class Configuration(C.Structure):
    _fields_=[('length',U8),('type',U8),('total',U16),('count',U8),('value',U8),
        ('string',U8),('attributes',U8),('power',U8),('interface',C.POINTER(Interface)),
        ('extra',C.c_void_p),('extra_length',C.c_int)]


class Transport:
    def __init__(self,library=None):
        if library is None:
            filename='libusb-1.0.dll' if sys.platform=='win32' else 'libusb-1.0.dylib'
            bundled=Path(__file__).parent/'native'/filename
            if bundled.is_file():library=bundled
            else:
                import libusb_package
                library=libusb_package.find_library('libusb-1.0')
        if not library:raise USBError('The bundled USB library is missing')
        self.lib=C.CDLL(str(library));self.context=C.c_void_p();self.handle=C.c_void_p()
        self.devices=C.POINTER(C.c_void_p)();self.claimed=False;self.identity=None
        if C.sizeof(Device)!=18 or C.sizeof(C.c_void_p)!=8:
            raise USBError('This build requires a supported 64-bit platform')
        if tuple(map(C.sizeof,(Endpoint,Alternate,Interface,Configuration)))!=(32,40,16,40):
            raise USBError('USB descriptor layout self-test failed')

    def function(self,name,result,args):
        f=getattr(self.lib,name);f.restype=result;f.argtypes=args;return f

    @staticmethod
    def check(label,status):
        if status<0:
            hints={-3:'USB access denied. Close other camera software and check the USB driver.',
                   -4:'The camera disconnected or went to sleep.',
                   -6:'Another program is using the service interface.',
                   -7:'USB timed out. Wake/reconnect the camera before trying again.',
                   -12:'Install WinUSB for this exact camera service interface on Windows.'}
            raise USBError(hints.get(status,label+' failed (libusb '+str(status)+')'))
        return status

    def string(self,index):
        if not index:return ''
        buf=(U8*256)()
        n=self.check('Read USB identity',self.function('libusb_get_string_descriptor_ascii',C.c_int,
            [C.c_void_p,U8,C.c_void_p,C.c_int])(self.handle,index,buf,len(buf)))
        return bytes(buf[:n]).decode('utf-8',errors='strict')

    def open(self):
        try:
            self.check('Initialize USB',self.function('libusb_init',C.c_int,[C.POINTER(C.c_void_p)])(C.byref(self.context)))
            n=self.check('Enumerate USB',self.function('libusb_get_device_list',C.c_ssize_t,
                [C.c_void_p,C.POINTER(C.POINTER(C.c_void_p))])(self.context,C.byref(self.devices)))
            if n>4096:raise USBError('USB device enumeration exceeded its bound')
            found=[];get=self.function('libusb_get_device_descriptor',C.c_int,[C.c_void_p,C.POINTER(Device)])
            for i in range(n):
                d=Device()
                if get(self.devices[i],C.byref(d))==0 and (d.vid,d.pid)==(0x04DA,0x2370):found.append((self.devices[i],d))
            if len(found)!=1:raise USBError('Connect exactly one awake Lumix in service mode (04DA:2370)')
            device,d=found[0];cfg=C.POINTER(Configuration)()
            self.check('Read USB configuration',self.function('libusb_get_config_descriptor',C.c_int,
                [C.c_void_p,U8,C.POINTER(C.POINTER(Configuration))])(device,0,C.byref(cfg)))
            try:
                c=cfg.contents
                if d.configurations!=1 or c.value!=1 or c.count!=1 or c.interface[0].count!=1:
                    raise USBError('Unsupported service USB configuration')
                a=c.interface[0].alternate[0]
                if (a.number,a.alternate,a.cls,a.sub,a.protocol,a.count)!=(0,0,255,160,176,3):
                    raise USBError('Unsupported service USB interface')
                ep=sorted((a.endpoint[i].address,a.endpoint[i].attributes&3,a.endpoint[i].packet) for i in range(3))
                if [(v,t) for v,t,_ in ep]!=[(1,2),(0x82,2),(0x83,3)] or any(s not in (64,512) for _,_,s in ep):
                    raise USBError('Unsupported service USB endpoints')
            finally:self.function('libusb_free_config_descriptor',None,[C.POINTER(Configuration)])(cfg)
            self.check('Open USB',self.function('libusb_open',C.c_int,[C.c_void_p,C.POINTER(C.c_void_p)])(device,C.byref(self.handle)))
            product=self.string(d.product)
            if product!='DMC-GM5':raise USBError('Detected '+product+'. Only the validated DMC-GM5 profile is currently supported.')
            self.identity=dict(model=product,serial=self.string(d.serial),usb_release=d.release)
            active=C.c_int()
            self.check('Read active USB configuration',self.function('libusb_get_configuration',C.c_int,
                [C.c_void_p,C.POINTER(C.c_int)])(self.handle,C.byref(active)))
            if active.value!=1:raise USBError('The service configuration is inactive; reconnect in service mode')
            self.check('Claim service USB',self.function('libusb_claim_interface',C.c_int,[C.c_void_p,C.c_int])(self.handle,0))
            self.claimed=True;return self
        except Exception:
            self.close();raise

    def prepare(self,index):
        status=self.check('Prepare USB direction',self.function('libusb_control_transfer',C.c_int,
            [C.c_void_p,U8,U8,U16,U16,C.c_void_p,U16,C.c_uint])(self.handle,0x40,0,0,index,None,0,1500))
        if status:raise USBError('Unexpected service-control reply length')

    def bulk(self,endpoint,data,size):
        buf=(U8*size)();actual=C.c_int()
        if data is not None:buf[:]=data
        self.check('Service USB transfer',self.function('libusb_bulk_transfer',C.c_int,
            [C.c_void_p,U8,C.c_void_p,C.c_int,C.POINTER(C.c_int),C.c_uint])(
                self.handle,endpoint,buf,size,C.byref(actual),1500))
        if actual.value!=size:raise USBError('Incomplete service USB transfer; stopped without retry')
        return bytes(buf)

    def exchange(self,request,kind,size):
        if not self.claimed:raise USBError('Service USB is not open')
        if (kind,size,len(request)) not in ((1,1030,1030),(8,16,16)):
            raise USBError('Unreviewed service transfer geometry')
        self.prepare(0);self.bulk(1,request,len(request));time.sleep(0.1)
        self.prepare(1)
        if self.bulk(0x82,None,1)!=bytes([kind]):raise USBError('Unexpected service response type')
        self.prepare(1);return self.bulk(0x82,None,size)

    def close(self):
        if self.handle:
            if self.claimed:self.function('libusb_release_interface',C.c_int,[C.c_void_p,C.c_int])(self.handle,0)
            self.function('libusb_close',None,[C.c_void_p])(self.handle)
        if self.devices:self.function('libusb_free_device_list',None,[C.POINTER(C.c_void_p),C.c_int])(self.devices,1)
        if self.context:self.function('libusb_exit',None,[C.c_void_p])(self.context)
        self.handle=C.c_void_p();self.context=C.c_void_p();self.devices=C.POINTER(C.c_void_p)();self.claimed=False

    def __enter__(self):return self.open()
    def __exit__(self,*_):self.close()
