"""Explicit reviewed model geometries; a shared USB ID is not a profile."""

MODELS={
    'DMC-GM5':dict(token='GM5',filename='GM5__V11.bin',
        official_page='https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm5.html',
        official_url='https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GM5__V11.zip',
        bin_sha='d4fd5721e5a6d54efc960c3ed7bc1300f62cf1eddf8b201e74c803a5d1886243',
        zip_sha='0e9be7b3bb0eb0378f67110efe3ef7657d7b7920f9a52e1534653029ef21e515',
        bin_size=31901184,zip_size=31905359,
        destinations={'program':0,'guires':0x800000,'program2':0x1400000},
        sizes={'program':0x800000,'guires':0xC00000,'program2':0x360000},
        lut_program_bytes=0x7A0000,
        profiles={0x0110:'gm5-official-0110',0x0111:'gm5-factory-0111'},
        policy_rom=0x406B1800,policy_rom_offset=0x3DC,policy_ram=0x70A68400,policy_ram_offset=0x90,
        mode=0x702FF800,mode_offset=0x5D,key_page=0x4064B400,key_offset=0xCC,
        key_sha='8c5c9a63324a7b65ec589672f479961f11523f393d846fab05d8fc66b61b94e5',
        duration_offset=0x19016F,duration_before='dd19941c',advertised=0x011F,
        format_duration_offset=0x157A07,format_duration_before='83a56bc00b2e0707fac96701c308fcce98b70000'),
    'DMC-GM1':dict(token='GM1',filename='GM1__V11.bin',
        official_page='https://av.jpn.support.panasonic.com/support/global/cs/dsc/download/fts/dl/gm1.html',
        official_url='https://av.jpn.support.panasonic.com/support/share/eww/en/dsc/fts/mac/GM1__V11.zip',
        bin_sha='3e8b4aab23f79db160cd016af0e466011f047add07bb7441c642f6b70df30d90',
        zip_sha='4dbff5b5cd05f288d96506290f8b001ecc55969cea63a61c9fa868cc3084c24b',
        bin_size=31983104,zip_size=31987180,
        destinations={'program':0,'guires':0x900000,'program2':0x1400000},
        sizes={'program':0x900000,'guires':0xB00000,'program2':0x360000},
        lut_program_bytes=0x880000,
        profiles={0x0110:'gm1-official-0110',0x0111:'gm1-factory-0111'},
        profile_overrides={0x0111:dict(policy_rom_offset=0x358,key_offset=0x78)},
        policy_rom=0x405C5800,policy_rom_offset=0x340,policy_ram=0x70903800,policy_ram_offset=0x14,
        mode=0x7024AC00,mode_offset=0x2AD,key_page=0x405AB400,key_offset=0x60,
        key_sha='555c3fdaafe1cda9d5eb941792bd9c3fac2153e1da17e1203c7c107f533344f5',
        duration_offset=0x1B0147,duration_before='dd46961a',advertised=0x0111,
        format_duration_offset=0x153193,format_duration_before='83a528c0092e0707a550c308fcce98b70000')}


def model_spec(model,revision=None):
    try:spec=MODELS[model]
    except (KeyError,TypeError):raise ValueError('Only the reviewed DMC-GM1 and DMC-GM5 profiles are supported') from None
    if revision is None:return spec
    if revision not in spec['profiles']:raise ValueError('The camera revision has no reviewed model profile')
    return dict(spec,**spec.get('profile_overrides',{}).get(revision,{}))
