"""Owned, deterministic PDF fixtures; never load a user's document."""
import zlib

def manual_pdf(pages=('Create a blank document. Type Hello. Verify Hello.','Use the plus button to add numbers.'),compressed=True,unicode=False,encrypted=False):
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>', b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    if unicode:
        characters=sorted(set(''.join(pages)))
        mappings={char:index+1 for index,char in enumerate(characters)}
        cmap=('begincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
              '/CMapName /Fixture def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'
              +str(len(characters))+' beginbfchar\n'+'\n'.join(f'<{mappings[char]:04X}> <{char.encode("utf-16-be").hex()}>' for char in characters)+'\nendbfchar\nendcmap').encode()
        objects[2]=b'<< /Type /Font /Subtype /Type0 /BaseFont /Fixture /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 5 0 R >>'
        objects += [b'<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Fixture /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> >>',b'<< /Length '+str(len(cmap)).encode()+b' >>\nstream\n'+cmap+b'\nendstream']
    refs=[]
    for text in pages:
        page=len(objects)+1;content=page+1;refs.append(f'{page} 0 R')
        literal=(b'<'+''.join(f'{mappings[char]:04X}' for char in text).encode()+b'>') if unicode else b'('+text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)').encode('cp1252')+b')'
        stream=b'BT /F1 12 Tf 50 720 Td '+literal+b' Tj ET'
        if compressed:stream=zlib.compress(stream)
        objects += [f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>'.encode(),b'<< /Length '+str(len(stream)).encode()+(b' /Filter /FlateDecode' if compressed else b'')+b' >>\nstream\n'+stream+b'\nendstream']
    objects[1]=f'<< /Type /Pages /Count {len(refs)} /Kids [{" ".join(refs)}] >>'.encode()
    extra=b''
    if encrypted:
        objects.append(b'<< /Filter /Standard /V 1 /R 2 /Length 40 /O <'+b'00'*32+b'> /U <'+b'00'*32+b'> /P -4 >>')
        extra=f' /Encrypt {len(objects)} 0 R /ID [<0123456789ABCDEF> <0123456789ABCDEF>]'.encode()
    raw=b'%PDF-1.4\n';offsets=[0]
    for n,obj in enumerate(objects,1):offsets.append(len(raw));raw+=f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(raw);raw+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()+b''.join(f'{off:010} 00000 n \n'.encode() for off in offsets[1:])
    return raw+f'trailer\n<< /Size {len(offsets)} /Root 1 0 R'.encode()+extra+f' >>\nstartxref\n{xref}\n%%EOF\n'.encode()
