"""Single-owner, bounded DevTools transport for our own local browser process."""
import base64
import hashlib
import json
import os
import socket
import struct
import time
from urllib.parse import urlsplit

MAX_MESSAGE=4*1024*1024


class DevTools:
    def __init__(self,url,port,guard=lambda:None):
        parsed=urlsplit(url)
        if parsed.scheme!='ws' or parsed.hostname!='127.0.0.1' or parsed.port!=port or parsed.username or parsed.password or not parsed.path.startswith('/devtools/browser/'):
            raise ValueError('DevTools must address the agent-owned loopback browser endpoint.')
        self.guard=guard;self.sequence=0;self.events=lambda event:None;self.buffer=b'';self.session=None
        self.socket=socket.create_connection(('127.0.0.1',port),timeout=5);self.socket.settimeout(.2)
        try:
            key=base64.b64encode(os.urandom(16)).decode()
            request=f'GET {parsed.path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n'
            self.socket.sendall(request.encode());deadline=time.monotonic()+5
            while b'\r\n\r\n' not in self.buffer:
                self._receive(deadline)
                if len(self.buffer)>16384:raise ValueError('Oversized browser handshake.')
            headers,self.buffer=self.buffer.split(b'\r\n\r\n',1)
            lines=headers.decode('ascii').split('\r\n');fields=dict(line.split(':',1) for line in lines[1:])
            fields={k.lower():v.strip() for k,v in fields.items()}
            expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if not lines[0].startswith('HTTP/1.1 101 ') or fields.get('sec-websocket-accept')!=expected:
                raise ValueError('Browser transport upgrade could not be authenticated.')
        except BaseException:self.socket.close();raise

    def _receive(self,deadline):
        self.guard()
        if time.monotonic()>deadline:raise TimeoutError('Browser command timed out.')
        try:data=self.socket.recv(65536)
        except socket.timeout:return
        if not data:raise ConnectionError('Browser connection closed.')
        self.buffer+=data

    def _read(self,count,deadline):
        while len(self.buffer)<count:self._receive(deadline)
        value,self.buffer=self.buffer[:count],self.buffer[count:];return value

    def _frame(self,payload,opcode=1):
        mask=os.urandom(4);size=len(payload)
        if size>MAX_MESSAGE:raise ValueError('Browser message exceeds the transport limit.')
        length=bytes([size|128]) if size<126 else bytes([126|128])+struct.pack('!H',size) if size<65536 else bytes([127|128])+struct.pack('!Q',size)
        self.socket.sendall(bytes([128|opcode])+length+mask+bytes(value^mask[index%4] for index,value in enumerate(payload)))

    def _message(self,deadline):
        pieces=[];size=0;started=False
        while True:
            a,b=self._read(2,deadline);opcode=a&15
            if a&0x70 or b&128:raise ValueError('Invalid browser websocket frame.')
            count=b&127
            if count==126:count=struct.unpack('!H',self._read(2,deadline))[0]
            elif count==127:count=struct.unpack('!Q',self._read(8,deadline))[0]
            if count>MAX_MESSAGE or size+count>MAX_MESSAGE:raise ValueError('Browser response exceeds the transport limit.')
            value=self._read(count,deadline)
            if opcode==8:raise ConnectionError('Browser closed the session.')
            if opcode in (9,10):
                if count>125 or not a&128:raise ValueError('Invalid browser control frame.')
                if opcode==9:self._frame(value,10)
                continue
            if opcode==1 and not started:started=True
            elif opcode!=0 or not started:raise ValueError('Unsupported browser websocket message.')
            pieces.append(value);size+=count
            if a&128:return json.loads(b''.join(pieces).decode('utf-8'))

    def send(self,method,params=None,session=None):
        self.sequence+=1;message={'id':self.sequence,'method':method,'params':params or {}}
        if session:message['sessionId']=session
        self._frame(json.dumps(message,separators=(',',':')).encode());return self.sequence

    def call(self,method,params=None,*,browser=False,timeout=20):
        self.guard();identity=self.send(method,params,None if browser else self.session);deadline=time.monotonic()+timeout
        while True:
            try:message=self._message(deadline)
            except TimeoutError as error:
                raise TimeoutError('Browser command timed out: '+method+'. Dispatch outcome may be unknown; do not retry an action automatically.') from error
            if message.get('id')==identity:
                if 'error' in message:raise RuntimeError('Browser command failed: '+str(message['error'].get('message','unknown'))[:200])
                return message.get('result',{})
            if 'method' in message:self.events(message)

    def close(self):self.socket.close()
