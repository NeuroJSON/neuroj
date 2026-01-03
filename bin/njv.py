#!/usr/bin/env python3
"""
jdbview.py - BJData/Binary JSON and JSON viewer
Usage: python3 jdbview.py file.jdb [--max-data 100] [--max-str 200] [--debug] [--big-endian]

BJData spec: https://neurojson.org/bjdata/draft3
"""
import sys
import struct
import json
import re
from collections import OrderedDict

def make_markers(big_endian=False):
    e = ">" if big_endian else "<"
    return {
        b'Z': ('null', 0, None),
        b'N': ('noop', 0, None),
        b'T': ('true', 0, None),
        b'F': ('false', 0, None),
        b'i': ('int8', 1, e + 'b'),
        b'U': ('uint8', 1, e + 'B'),
        b'I': ('int16', 2, e + 'h'),
        b'u': ('uint16', 2, e + 'H'),
        b'l': ('int32', 4, e + 'i'),
        b'm': ('uint32', 4, e + 'I'),
        b'L': ('int64', 8, e + 'q'),
        b'M': ('uint64', 8, e + 'Q'),
        b'h': ('float16', 2, e + 'e'),
        b'd': ('float32', 4, e + 'f'),
        b'D': ('float64', 8, e + 'd'),
        b'C': ('char', 1, e + 'B'),
        b'B': ('byte', 1, e + 'B'),
        b'S': ('string', -1, None),
        b'H': ('highprec', -1, None),
        b'[': ('array', -1, None),
        b']': ('array_end', 0, None),
        b'{': ('object', -1, None),
        b'}': ('object_end', 0, None),
        b'$': ('type', 0, None),
        b'#': ('count', 0, None),
    }

INT_TYPES = {b'i', b'U', b'I', b'u', b'l', b'm', b'L', b'M'}


class BJDataReader:
    def __init__(self, data, max_data=100, max_str=200, debug=False, big_endian=False):
        self.data = data
        self.pos = 0
        self.max_data = max_data
        self.max_str = max_str
        self.debug = debug
        self.depth = 0
        self.markers = make_markers(big_endian)
    
    def log(self, msg):
        if self.debug:
            print("# " + str(self.pos).rjust(6) + ": " + "  " * self.depth + msg)
    
    def remaining(self):
        return len(self.data) - self.pos
    
    def read(self, n):
        if self.pos + n > len(self.data):
            raise EOFError("EOF at " + str(self.pos) + ", need " + str(n) + ", have " + str(self.remaining()))
        result = self.data[self.pos:self.pos + n]
        self.pos += n
        return result
    
    def peek(self, n=1):
        return self.data[self.pos:self.pos + n]
    
    def read_int(self, marker=None):
        if marker is None:
            marker = self.read(1)
        if marker not in INT_TYPES:
            raise ValueError("Expected int marker, got " + repr(marker) + " at " + str(self.pos))
        _, size, fmt = self.markers[marker]
        return struct.unpack(fmt, self.read(size))[0]
    
    def read_num(self, marker):
        _, size, fmt = self.markers[marker]
        return struct.unpack(fmt, self.read(size))[0]
    
    def read_value(self):
        marker = self.read(1)
        self.log("marker: " + (chr(marker[0]) if 32 <= marker[0] < 127 else marker.hex()))
        
        if marker == b'Z': return None
        if marker == b'N': return self.read_value()
        if marker == b'T': return True
        if marker == b'F': return False
        
        if marker in {b'i', b'U', b'I', b'u', b'l', b'm', b'L', b'M', b'h', b'd', b'D'}:
            return self.read_num(marker)
        if marker == b'C':
            return self.read(1).decode('ascii', errors='replace')
        if marker == b'B':
            return self.read(1)[0]
        if marker == b'S':
            length = self.read_int()
            if length == 0:
                return ""
            raw = self.read(length)
            try:
                return raw.decode('utf-8')
            except:
                return raw.decode('latin-1')
        if marker == b'H':
            length = self.read_int()
            return "HighPrec(" + self.read(length).decode() + ")"
        if marker == b'[':
            self.log("array [")
            return self.read_array()
        if marker == b'{':
            self.log("object {")
            return self.read_object()
        
        raise ValueError("Unknown marker " + repr(marker) + " at " + str(self.pos - 1))
    
    def read_typed_array(self, elem_type, count):
        name, size, fmt = self.markers[elem_type]
        total_bytes = count * size
        if total_bytes > self.remaining():
            avail = self.remaining()
            raw = self.read(avail) if avail > 0 else b''
            return "<" + name + "[" + str(count) + "]: " + (raw[:32].hex() if avail > 0 else "") + "... (truncated: " + str(avail) + "B of " + str(total_bytes) + "B)>"
        if count > self.max_data:
            n = min(8, count)
            vals = [struct.unpack(fmt, self.read(size))[0] for _ in range(n)]
            self.read((count - n) * size)
            return "<" + name + "[" + str(count) + "]: " + str(vals[:4]) + "... (" + str(total_bytes) + "B)>"
        return [struct.unpack(fmt, self.read(size))[0] for _ in range(count)]
    
    def read_array(self):
        elem_type = None
        count = None
        self.depth += 1
        
        if self.peek() == b'$':
            self.read(1)
            elem_type = self.read(1)
            self.log("type: " + chr(elem_type[0]))
        
        if self.peek() == b'#':
            self.read(1)
            if self.peek() == b'[':
                self.read(1)
                col_major = False
                if self.peek() == b'[':
                    self.read(1)
                    col_major = True
                dims = self.read_dims()
                if col_major and self.peek() == b']':
                    self.read(1)
                result = self.read_nd(elem_type, dims, col_major)
                self.depth -= 1
                return result
            else:
                self.log("count marker: " + str(self.peek()))
                count = self.read_int()
                self.log("count: " + str(count))
        
        if count is not None and elem_type is not None:
            result = self.read_typed_array(elem_type, count)
        elif count is not None:
            result = [self.read_value() for _ in range(count)]
        else:
            result = []
            while self.peek() != b']':
                result.append(self.read_value())
            self.read(1)
            self.log("array ]")
        self.depth -= 1
        return result
    
    def read_dims(self):
        dims = []
        elem_type = None
        count = None
        if self.peek() == b'$':
            self.read(1)
            elem_type = self.read(1)
        if self.peek() == b'#':
            self.read(1)
            count = self.read_int()
        if count and elem_type:
            _, size, fmt = self.markers[elem_type]
            dims = [struct.unpack(fmt, self.read(size))[0] for _ in range(count)]
        elif count:
            dims = [self.read_int() for _ in range(count)]
        else:
            while self.peek() != b']':
                dims.append(self.read_value())
            self.read(1)
        self.log("dims: " + str(dims))
        return dims
    
    def read_nd(self, elem_type, dims, col_major):
        total = 1
        for d in dims:
            total *= d
        name, size, fmt = self.markers[elem_type]
        total_bytes = total * size
        order = "col" if col_major else "row"
        if total_bytes > self.remaining():
            avail = self.remaining()
            raw = self.read(avail) if avail > 0 else b''
            return "<" + name + str(dims) + " " + order + ": " + (raw[:32].hex() if avail > 0 else "") + "... (truncated: " + str(avail) + "B of " + str(total_bytes) + "B)>"
        if total > self.max_data:
            n = min(8, total)
            vals = [struct.unpack(fmt, self.read(size))[0] for _ in range(n)]
            self.read((total - n) * size)
            return "<" + name + str(dims) + " " + order + ": " + str(vals[:4]) + "... (" + str(total_bytes) + "B)>"
        data = [struct.unpack(fmt, self.read(size))[0] for _ in range(total)]
        return "<" + name + str(dims) + " " + order + ": " + str(data) + ">"
    
    def read_object(self):
        elem_type = None
        count = None
        self.depth += 1
        
        if self.peek() == b'$':
            self.read(1)
            elem_type = self.read(1)
            self.log("type: " + chr(elem_type[0]))
        if self.peek() == b'#':
            self.read(1)
            count = self.read_int()
            self.log("count: " + str(count))
        
        result = OrderedDict()
        def read_entry():
            klen = self.read_int()
            raw_key = self.read(klen)
            try:
                key = raw_key.decode('utf-8')
            except:
                key = raw_key.decode('latin-1')
            self.log("key: " + key)
            if elem_type:
                _, size, fmt = self.markers[elem_type]
                result[key] = struct.unpack(fmt, self.read(size))[0]
            else:
                result[key] = self.read_value()
        
        if count is not None:
            for _ in range(count):
                read_entry()
        else:
            while self.peek() != b'}':
                read_entry()
            self.read(1)
            self.log("object }")
        self.depth -= 1
        return result


def truncate_str(s, max_str):
    if len(s) <= max_str:
        return s
    half = max_str // 2
    return s[:half] + "..." + s[-half:] + " (" + str(len(s)) + " chars)"


def fmt_val(v, max_data=100, max_str=200, ind=0):
    p = "  " * ind
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        if v.startswith("<") and "..." in v:
            return v
        return '"' + truncate_str(v, max_str) + '"'
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        if len(v) > max_data:
            preview = ", ".join(fmt_val(x, max_data, max_str) for x in v[:4])
            return "<array[" + str(len(v)) + "]: [" + preview + ", ...]>"
        if len(v) <= 10 and all(isinstance(x, (int, float)) for x in v):
            s = "[" + ", ".join(fmt_val(x, max_data, max_str) for x in v) + "]"
            if len(s) < 80:
                return s
        lines = ["["] + [p + "  " + fmt_val(x, max_data, max_str, ind + 1) + "," for x in v] + [p + "]"]
        return "\n".join(lines)
    if isinstance(v, dict):
        if not v:
            return "{}"
        keys = list(v.keys())
        if len(keys) > max_data:
            preview = ", ".join('"' + str(k) + '": ' + fmt_val(v[k], max_data, max_str) for k in keys[:4])
            return "<object[" + str(len(keys)) + " keys]: { " + preview + ", ... }>"
        lines = ["{"] + [p + '  "' + str(k) + '": ' + fmt_val(x, max_data, max_str, ind + 1) + "," for k, x in v.items()] + [p + "}"]
        return "\n".join(lines)
    return str(v)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 jdbview.py <file> [--max-data N] [--max-str N] [--debug] [--big-endian]")
        print("\nBJData/JSON viewer. Use --big-endian for UBJSON/BJData Draft 1 files.")
        sys.exit(1)
    
    fn = sys.argv[1]
    max_data = 100
    max_str = 200
    debug = "--debug" in sys.argv
    be = "--big-endian" in sys.argv or "--be" in sys.argv
    
    if "--max-data" in sys.argv:
        max_data = int(sys.argv[sys.argv.index("--max-data") + 1])
    if "--max-str" in sys.argv:
        max_str = int(sys.argv[sys.argv.index("--max-str") + 1])
    
    with open(fn, "rb") as f:
        data = f.read()
    
    print("# File: " + fn + " (" + str(len(data)) + " bytes)")
    if be:
        print("# Mode: Big-endian (UBJSON/BJData Draft 1)")
    print()
    
    if debug:
        print("# First 256 bytes:")
        for i in range(0, min(256, len(data)), 16):
            c = data[i:i + 16]
            h = c.hex()
            a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in c)
            print("  " + str(i).zfill(4) + ": " + h + "  " + a)
        print()
    
    # Detect JSON vs BJData
    # JSON: { followed by " or whitespace, [ followed by " or digit or whitespace
    # BJData: { or [ followed by type markers (U, i, $, #, etc.)
    first = data[:2]
    is_json = False
    if len(first) >= 2 and chr(first[0]) in '{[':
        second = chr(first[1])
        if second in ' \t\n\r"0123456789-[{':
            is_json = True
    
    if is_json:
        try:
            text = data.decode('utf-8')
            v = json.loads(text, object_pairs_hook=OrderedDict)
            print(fmt_val(v, max_data, max_str))
            return
        except Exception as e:
            if debug:
                print("# JSON parse failed: " + str(e))
    
    # BJData parsing
    r = BJDataReader(data, max_data, max_str, debug, be)
    try:
        v = r.read_value()
        print(fmt_val(v, max_data, max_str))
        if r.remaining() > 0:
            print("\n# " + str(r.remaining()) + " bytes remaining")
    except Exception as e:
        print("Error at " + str(r.pos) + ": " + str(e))
        s = max(0, r.pos - 32)
        e2 = min(len(data), r.pos + 64)
        print("\nHex [" + str(s) + ":" + str(e2) + "]:")
        for i in range(s, e2, 16):
            c = data[i:min(i + 16, e2)]
            print("  " + str(i).zfill(4) + ": " + c.hex() + "  " + ''.join(chr(b) if 32 <= b < 127 else '.' for b in c))


if __name__ == "__main__":
    main()