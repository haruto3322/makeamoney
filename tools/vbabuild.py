"""Build a vbaProject.bin from module source (MS-OVBA 2.3.4.2 dir stream)."""
import struct
import ovba

CODEPAGE = 932            # Shift-JIS (Japanese)
ENC = 'cp932'


def _rec(rid, payload):
    return struct.pack('<HI', rid, len(payload)) + payload


def _rec_fixed(rid, size, payload):
    return struct.pack('<HI', rid, size) + payload


class Module:
    def __init__(self, name, source, is_document, codepage=CODEPAGE):
        self.name = name
        self.source = source        # str
        self.is_document = is_document
        self.stream_name = name

    def stream_bytes(self):
        return ovba.compress(self.source.encode(ENC))


def build_dir(project_name, modules, constants=''):
    b = bytearray()
    # ---- PROJECTINFORMATION ----
    b += _rec_fixed(0x0001, 4, struct.pack('<I', 0x00000001))          # SysKind Win32
    b += _rec_fixed(0x0002, 4, struct.pack('<I', 0x00000409))          # Lcid
    b += _rec_fixed(0x0014, 4, struct.pack('<I', 0x00000409))          # LcidInvoke
    b += _rec_fixed(0x0003, 2, struct.pack('<H', CODEPAGE))            # CodePage
    pn = project_name.encode(ENC)
    b += _rec(0x0004, pn)                                              # ProjectName
    # DocString
    b += struct.pack('<HI', 0x0005, 0) + struct.pack('<H', 0x0040) + struct.pack('<I', 0)
    # HelpFilePath
    b += struct.pack('<HI', 0x0006, 0) + struct.pack('<H', 0x003D) + struct.pack('<I', 0)
    b += _rec_fixed(0x0007, 4, struct.pack('<I', 0))                   # HelpContext
    b += _rec_fixed(0x0008, 4, struct.pack('<I', 0))                   # LibFlags
    # Version: Id=0x0009, Reserved=4, Major(4), Minor(2)
    b += struct.pack('<HI', 0x0009, 4) + struct.pack('<I', 1) + struct.pack('<H', 6)
    # Constants
    cb = constants.encode(ENC)
    cu = constants.encode('utf-16-le')
    b += struct.pack('<HI', 0x000C, len(cb)) + cb + struct.pack('<H', 0x003C) + struct.pack('<I', len(cu)) + cu

    # ---- PROJECTMODULES ----
    b += _rec_fixed(0x000F, 2, struct.pack('<H', len(modules)))        # module count
    b += _rec_fixed(0x0013, 2, struct.pack('<H', 0xFFFF))             # cookie
    for m in modules:
        nm = m.name.encode(ENC)
        nu = m.name.encode('utf-16-le')
        sn = m.stream_name.encode(ENC)
        su = m.stream_name.encode('utf-16-le')
        b += _rec(0x0019, nm)                                          # MODULENAME
        b += _rec(0x0047, nu)                                          # MODULENAMEUNICODE
        b += struct.pack('<HI', 0x001A, len(sn)) + sn + struct.pack('<H', 0x0032) + struct.pack('<I', len(su)) + su
        b += struct.pack('<HI', 0x001C, 0) + struct.pack('<H', 0x0048) + struct.pack('<I', 0)  # docstring
        b += _rec_fixed(0x0031, 4, struct.pack('<I', 0))              # MODULEOFFSET TextOffset=0
        b += _rec_fixed(0x001E, 4, struct.pack('<I', 0))             # HelpContext
        b += _rec_fixed(0x002C, 2, struct.pack('<H', 0xFFFF))        # Cookie
        mtype = 0x0022 if m.is_document else 0x0021
        b += struct.pack('<HI', mtype, 0)                            # MODULETYPE
        b += struct.pack('<HI', 0x002B, 0)                          # module terminator
    # ---- Terminator ----
    b += struct.pack('<HI', 0x0010, 0)
    return ovba.compress(bytes(b))


def build_project_stream(project_name, modules):
    doc_lines = [m for m in modules if m.is_document]
    std_lines = [m for m in modules if not m.is_document]
    lines = []
    lines.append('ID="{5DE96CC0-9C3A-4B32-8A9F-1234567890AB}"')
    for m in doc_lines:
        lines.append('Document=%s/&H00000000' % m.name)
    for m in std_lines:
        lines.append('Module=%s' % m.name)
    lines.append('Name="%s"' % project_name)
    lines.append('HelpContextID="0"')
    lines.append('VersionCompatible32="393222000"')
    lines.append('')
    lines.append('[Host Extender Info]')
    lines.append('&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;&H00000000')
    lines.append('')
    lines.append('[Workspace]')
    for m in modules:
        lines.append('%s=0, 0, 0, 0, C' % m.name)
    text = '\r\n'.join(lines) + '\r\n'
    return text.encode(ENC)


def build_projectwm(modules):
    b = bytearray()
    for m in modules:
        b += m.name.encode(ENC) + b'\x00'
        b += m.name.encode('utf-16-le') + b'\x00\x00'
    b += b'\x00\x00'
    return bytes(b)


def build_vba_project_stream():
    # Reserved1=0x61CC, Version=0xFFFF (force recompile from source), Reserved2, Reserved3
    return struct.pack('<H', 0x61CC) + struct.pack('<H', 0xFFFF) + b'\x00' + struct.pack('<H', 0x0000)


def build(project_name, modules):
    cf = ovba.CFB()
    cf.add_stream('', 'PROJECT', build_project_stream(project_name, modules))
    cf.add_stream('', 'PROJECTwm', build_projectwm(modules))
    cf.add_storage('VBA')
    cf.add_stream('VBA', '_VBA_PROJECT', build_vba_project_stream())
    cf.add_stream('VBA', 'dir', build_dir(project_name, modules))
    for m in modules:
        cf.add_stream('VBA', m.stream_name, m.stream_bytes())
    return cf.write()
