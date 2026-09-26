"""Container-level scanning for C2PA JUMBF boxes and ordinary metadata.

Pure-Python parsers for PNG and JPEG; other formats fall back to a byte scan.
"""

from __future__ import annotations

import struct
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def sniff_format(data: bytes) -> str:
    if data.startswith(PNG_SIG):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[4:8] == b"ftyp":
        return "isobmff"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:5] == b"%PDF-":
        return "pdf"
    return "unknown"


def _png_chunks(data: bytes):
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        yield ctype.decode("latin-1"), body
        pos += 12 + length
        if ctype == b"IEND":
            break


def _jpeg_segments(data: bytes):
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if marker == 0xDA:  # start of scan: metadata segments are before it
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        yield marker, data[pos + 4:pos + 2 + length]
        pos += 2 + length


def scan_container(path: str | Path) -> dict:
    data = Path(path).read_bytes()
    fmt = sniff_format(data)
    meta: dict = {"format": fmt, "size_bytes": len(data), "metadata": {}}
    jumbf = []
    if fmt == "png":
        text_chunks, other = {}, []
        for ctype, body in _png_chunks(data):
            if ctype == "caBX":
                jumbf.append({"container": "png:caBX", "bytes": len(body),
                              "has_c2pa_label": b"c2pa" in body[:256]})
            elif ctype in ("tEXt", "iTXt", "zTXt"):
                key = body.split(b"\x00", 1)[0].decode("latin-1", "replace")
                text_chunks[key] = len(body)
            elif ctype not in ("IHDR", "IDAT", "IEND", "PLTE"):
                other.append(ctype)
        meta["metadata"] = {"text_chunks": text_chunks, "ancillary_chunks": other,
                            "exif": "eXIf" in other, "icc_profile": "iCCP" in other,
                            "xmp": "XML:com.adobe.xmp" in text_chunks}
    elif fmt == "jpeg":
        segs = []
        exif = xmp = icc = False
        for marker, body in _jpeg_segments(data):
            name = f"APP{marker - 0xE0}" if 0xE0 <= marker <= 0xEF else f"0x{marker:02X}"
            segs.append(name)
            if marker == 0xE1 and body.startswith(b"Exif"):
                exif = True
            if marker == 0xE1 and body.startswith(b"http://ns.adobe.com/xap/1.0/"):
                xmp = True
            if marker == 0xE2 and body.startswith(b"ICC_PROFILE"):
                icc = True
            if marker == 0xEB and body[:2] == b"JP":
                jumbf.append({"container": "jpeg:APP11", "bytes": len(body),
                              "has_c2pa_label": b"c2pa" in body[:512]})
        meta["metadata"] = {"segments": segs, "exif": exif, "xmp": xmp, "icc_profile": icc}
    else:
        idx = data.find(b"jumb")
        if idx >= 0:
            jumbf.append({"container": f"{fmt}:byte-scan", "offset": idx,
                          "has_c2pa_label": b"c2pa" in data[idx:idx + 512]})
        meta["metadata"] = {"xmp": b"http://ns.adobe.com/xap/1.0/" in data}
    meta["jumbf_boxes"] = jumbf
    meta["c2pa_bytes_found"] = any(j["has_c2pa_label"] for j in jumbf) or bool(jumbf)
    meta["xmp_provenance_reference"] = b"dcterms:provenance" in data
    return meta
