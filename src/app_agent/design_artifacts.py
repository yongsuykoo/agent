"""Check actual exported PSD/PNG bytes, independently of planner completion."""
import hashlib
import math
from pathlib import Path
import struct
import zlib

MAX_FILE = 256_000_000


def layer_names(design):
    return ['Agent base'] + ['Agent shape ' + str(i+1) for i in range(len(design['shapes']))] + ['Agent text ' + str(i+1) for i in range(len(design['texts']))]


def _path(path, root):
    path, root = Path(path), Path(root)
    if path.is_symlink() or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [path.parent, *path.parents]):
        raise ValueError('Artifact paths cannot follow symbolic links or junctions.')
    if path.parent.resolve() != root.resolve() or not path.is_file() or not 1 <= path.stat().st_size <= MAX_FILE:
        raise ValueError('Artifact missing, outside its task folder or exceeds the file allowance.')
    return path


def _digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            value.update(block)
    return value.hexdigest()


def psd_info(path):
    size = path.stat().st_size
    with path.open('rb') as f:
        def read(n):
            value = f.read(n)
            if len(value) != n:
                raise ValueError('Truncated PSD structure.')
            return value
        def number(): return struct.unpack('>I', read(4))[0]
        header = read(26)
        if header[:4] != b'8BPS' or header[4:6] != b'\0\1' or header[6:12] != bytes(6):
            raise ValueError('Not a supported PSD document.')
        channels, height, width, depth, mode = struct.unpack('>HIIHH', header[12:])
        if not 1 <= channels <= 56 or depth != 8 or mode != 3:
            raise ValueError('Expected an 8-bit RGB PSD.')
        for _ in range(2):
            length = number()
            if f.tell() + length > size:
                raise ValueError('Invalid PSD section length.')
            f.seek(length, 1)
        mask_size = number(); mask_end = f.tell() + mask_size
        if mask_end > size or mask_size < 6:
            raise ValueError('PSD has no readable layer structure.')
        info_size = number(); info_end = f.tell() + info_size
        if info_end > mask_end or info_size < 2:
            raise ValueError('Invalid PSD layer section.')
        count = abs(struct.unpack('>h', read(2))[0])
        if not 1 <= count <= 21:
            raise ValueError('Unexpected PSD layer count.')
        names, channel_lengths = [], []
        for _ in range(count):
            read(16); channel_count = struct.unpack('>H', read(2))[0]
            if channel_count > 56:
                raise ValueError('Invalid PSD layer channels.')
            for _ in range(channel_count):
                read(2); channel_lengths.append(number())
            if read(4) != b'8BIM':
                raise ValueError('Invalid PSD blend signature.')
            read(8); extra_size = number(); extra_end = f.tell() + extra_size
            if extra_end > info_end:
                raise ValueError('Invalid PSD layer metadata length.')
            for _ in range(2):
                n = number()
                if f.tell() + n > extra_end:
                    raise ValueError('Invalid PSD layer metadata.')
                f.seek(n, 1)
            n = read(1)[0]
            if f.tell() + n > extra_end:
                raise ValueError('Invalid PSD layer name.')
            names.append(read(n).decode('ascii', errors='replace'))
            f.seek(extra_end)
        if f.tell() + sum(channel_lengths) > info_end:
            raise ValueError('PSD layer pixels exceed their layer section.')
        f.seek(mask_end)
        compression = struct.unpack('>H', read(2))[0]
        expected = width * height * channels
        if not 1 <= width <= 4096 or not 1 <= height <= 4096 or expected > MAX_FILE:
            raise ValueError('PSD dimensions exceed the supported export bounds.')
        if compression == 0:
            if size - f.tell() != expected:
                raise ValueError('PSD composite pixel data is incomplete.')
        elif compression == 1:
            counts = [struct.unpack('>H', read(2))[0] for _ in range(height * channels)]
            if sum(counts) != size - f.tell():
                raise ValueError('PSD compressed pixel lengths do not match the file.')
            for count in counts:
                encoded = read(count); offset = decoded = 0
                while offset < count:
                    flag = encoded[offset]; offset += 1
                    if flag < 128:
                        n = flag + 1; offset += n; decoded += n
                    elif flag > 128:
                        offset += 1; decoded += 257 - flag
                    if offset > count or decoded > width:
                        raise ValueError('PSD PackBits row is corrupt.')
                if decoded != width:
                    raise ValueError('PSD PackBits row is incomplete.')
        elif compression in (2, 3):
            decoder = zlib.decompressobj()
            pixels = decoder.decompress(f.read(), expected + 1)
            if len(pixels) != expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                raise ValueError('PSD zipped composite pixel data is invalid.')
        else:
            raise ValueError('Unsupported PSD composite compression.')
        return {'width': width, 'height': height, 'layers': names, 'depth': depth, 'mode': 'RGB'}


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def png_info(path, expected_size):
    with path.open('rb') as f:
        if f.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Not a PNG image.')
        data, header, chunks, end = bytearray(), None, 0, False
        while not end:
            chunks += 1
            prefix = f.read(8)
            if len(prefix) != 8 or chunks > 10000:
                raise ValueError('Invalid PNG structure.')
            n, kind = struct.unpack('>I4s', prefix)
            if n > MAX_FILE or f.tell() + n + 4 > path.stat().st_size:
                raise ValueError('Invalid PNG chunk length.')
            payload = f.read(n); crc = f.read(4)
            if len(crc) != 4 or struct.unpack('>I', crc)[0] != zlib.crc32(kind + payload) & 0xffffffff:
                raise ValueError('PNG checksum mismatch.')
            if kind == b'IHDR':
                if header is not None or chunks != 1 or n != 13:
                    raise ValueError('Invalid PNG header.')
                header = struct.unpack('>IIBBBBB', payload)
            elif kind == b'IDAT':
                data.extend(payload)
            elif kind == b'IEND':
                if n != 0 or f.read(1):
                    raise ValueError('Invalid PNG end.')
                end = True
        if not header:
            raise ValueError('PNG dimensions are absent.')
        width, height, depth, color, compression, filtering, interlace = header
        if [width, height] != list(expected_size) or depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)):
            raise ValueError('PNG dimensions/encoding do not match the intended 8-bit RGB logo.')
        bpp = 4 if color == 6 else 3
        expected = height * (width * bpp + 1)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(data, expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError('PNG pixel stream is incomplete or exceeds its expected size.')
        stride = width * bpp; previous = bytearray(stride); colors = set(); visible = 0; transparent = 0
        for y in range(height):
            start = y * (stride + 1); method = raw[start]; row = bytearray(raw[start+1:start+stride+1])
            if method > 4:
                raise ValueError('Unsupported PNG scanline filter.')
            if method:
                for x in range(stride):
                    a = row[x-bpp] if x >= bpp else 0; b = previous[x]; c = previous[x-bpp] if x >= bpp else 0
                    predictor = a if method == 1 else b if method == 2 else (a+b)//2 if method == 3 else _paeth(a,b,c)
                    row[x] = (row[x]+predictor) & 255
            for x in range(0, stride, bpp):
                alpha = row[x+3] if bpp == 4 else 255
                if alpha:
                    visible += 1
                    # Bound color evidence memory for antialiased images.
                    if len(colors) < 65536: colors.add(tuple(row[x:x+3]))
                else: transparent += 1
            previous = row
        if visible < max(8, width * height // 10000) or (len(colors) < 2 and not transparent):
            raise ValueError('PNG is blank or a uniform opaque image; no logo content verified.')
        return {'width': width, 'height': height, 'visible_pixels': visible, 'transparent_pixels': transparent,
                'colors': sorted(colors), 'pixel_content_checked': True}


def verify_exports(directory, design, observed):
    directory = Path(directory)
    psd, png = _path(directory/'logo.psd', directory), _path(directory/'logo.png', directory)
    expected_names = layer_names(design)
    if observed.get('width') != design['width'] or observed.get('height') != design['height'] or sorted(observed.get('layers', [])) != sorted(expected_names):
        raise ValueError('Observed Photoshop document dimensions/layers differ from the plan.')
    if observed.get('texts') != [t['text'] for t in design['texts']]:
        raise ValueError('Photoshop text contents differ from the requested design.')
    if observed.get('fonts') != [t['font'] for t in design['texts']]:
        raise ValueError('Photoshop substituted a planned font.')
    bounds = observed.get('text_bounds')
    if not isinstance(bounds, list) or len(bounds) != len(design['texts']):
        raise ValueError('Photoshop text fitting evidence is missing.')
    for box in bounds:
        if not isinstance(box, list) or len(box) != 4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in box) or not (0 <= box[0] < box[2] <= design['width'] and 0 <= box[1] < box[3] <= design['height']):
            raise ValueError('Photoshop text is clipped or has invalid bounds.')
    native_psd = psd_info(psd)
    if [native_psd['width'], native_psd['height']] != [design['width'], design['height']] or sorted(native_psd['layers']) != sorted(expected_names):
        raise ValueError('Exported PSD dimensions/layers differ from the observed design.')
    native_png = png_info(png, [design['width'], design['height']])
    if design['background'] is None and not native_png['transparent_pixels']:
        raise ValueError('Transparent logo export lost its transparent background.')
    if design['background'] is not None and native_png['transparent_pixels']:
        raise ValueError('Opaque background export contains unexpected transparency.')
    palette = {c.upper() for c in [design['background'], *[p['color'] for p in design['shapes']], *[p['color'] for p in design['texts']]] if c}
    for color in palette:
        rgb = tuple(int(color[i:i+2],16) for i in (1,3,5))
        if not any(max(abs(a-b) for a,b in zip(rgb,pixel)) <= 4 for pixel in native_png['colors']):
            raise ValueError('A planned color is missing from the actual PNG pixels: ' + color)
    return {'status': 'artifact_verified', 'psd': native_psd, 'png': {k:v for k,v in native_png.items() if k != 'colors'},
            'files': [{'path': str(p), 'bytes': p.stat().st_size, 'sha256': _digest(p)} for p in (psd,png)],
            'scope': 'Photoshop DOM literal text/font/bounds, PSD structure/composite encoding, PNG dimensions/pixels/palette/transparency verified; aesthetic quality and exported PSD text editing are not independently certified.'}
