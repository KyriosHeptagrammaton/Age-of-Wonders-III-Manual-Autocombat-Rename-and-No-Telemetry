"""Small, read-only PE32 reader used by the version-specific patch builder."""
import struct


class PE:
    def __init__(self, data):
        self.data = data
        if data[:2] != b'MZ':
            raise ValueError('Not an MZ executable')
        self.pe = self.u32(0x3c)
        if data[self.pe:self.pe + 4] != b'PE\0\0':
            raise ValueError('Not a PE executable')
        self.count = self.u16(self.pe + 6)
        self.optional = self.pe + 24
        if self.u16(self.optional) != 0x10b:
            raise ValueError('Expected PE32')
        self.base = self.u32(self.optional + 28)
        self.table = self.optional + self.u16(self.pe + 20)
        self.sections = []
        for i in range(self.count):
            at = self.table + 40 * i
            name = bytes(data[at:at + 8]).rstrip(b'\0').decode('ascii')
            vs, rva, size, raw = struct.unpack_from('<IIII', data, at + 8)
            self.sections.append(dict(name=name, rva=rva, virtual_size=vs,
                                      raw=raw, size=size, header=at))

    def u16(self, at):
        return struct.unpack_from('<H', self.data, at)[0]

    def u32(self, at):
        return struct.unpack_from('<I', self.data, at)[0]

    def raw(self, rva):
        if rva < self.u32(self.optional + 60):
            return rva
        for s in self.sections:
            if s['rva'] <= rva < s['rva'] + s['size']:
                return s['raw'] + rva - s['rva']
        raise ValueError(f'RVA {rva:#x} has no file data')

    def string(self, rva):
        at = self.raw(rva)
        return bytes(self.data[at:self.data.index(0, at)]).decode('ascii')

    def imports(self):
        desc = self.raw(self.u32(self.optional + 104))
        result = {}
        while self.u32(desc + 12):
            dll = self.string(self.u32(desc + 12))
            lookup, iat = self.u32(desc), self.u32(desc + 16)
            at = self.raw(lookup or iat)
            index = 0
            while (entry := self.u32(at + 4 * index)):
                name = (f'#{entry & 0xffff}' if entry & 0x80000000
                        else self.string(entry + 2))
                result[(dll.lower(), name)] = iat + 4 * index
                index += 1
            desc += 20
        return result

    def validate_image_layout(self):
        """Check PE image section layout, including adjacency after alignment.

        Instruction emulators map raw bytes themselves and miss these loader
        requirements. This validates the file layout, not a Windows launch.
        """
        section_align = self.u32(self.optional + 32)
        file_align = self.u32(self.optional + 36)
        headers = self.u32(self.optional + 60)
        def align(n, a):
            return (n + a - 1) // a * a
        if (not section_align or section_align & (section_align - 1)
                or not file_align or file_align & (file_align - 1)):
            raise ValueError('Invalid PE alignment')
        if section_align < file_align or headers % file_align:
            raise ValueError('Invalid PE header alignment')
        if self.table + 40 * self.count > headers or headers > len(self.data):
            raise ValueError('Section headers do not fit SizeOfHeaders')
        next_rva = align(headers, section_align)
        raw_ranges = []
        for s in self.sections:
            if s['rva'] != next_rva:
                raise ValueError(f"Non-adjacent image section {s['name']}: "
                                 f"expected {next_rva:#x}, got {s['rva']:#x}")
            if s['size']:
                if (s['raw'] < headers or s['raw'] % file_align
                        or s['size'] % file_align
                        or s['raw'] + s['size'] > len(self.data)):
                    raise ValueError(f"Invalid raw section range: {s['name']}")
                raw_ranges.append((s['raw'], s['raw'] + s['size']))
            elif s['raw']:
                raise ValueError(f"Uninitialized section has a raw pointer: {s['name']}")
            next_rva = s['rva'] + align(max(s['virtual_size'], s['size']), section_align)
        raw_ranges.sort()
        if any(a[1] > b[0] for a, b in zip(raw_ranges, raw_ranges[1:])):
            raise ValueError('Overlapping raw sections')
        if next_rva != self.u32(self.optional + 56):
            raise ValueError('SizeOfImage does not match aligned section end')


def checksum(data, checksum_offset):
    total = 0
    for at in range(0, len(data), 2):
        word = 0 if checksum_offset <= at < checksum_offset + 4 else int.from_bytes(data[at:at + 2], 'little')
        total += word
        total = (total & 0xffff) + (total >> 16)
    total = (total & 0xffff) + (total >> 16)
    return total + len(data)
