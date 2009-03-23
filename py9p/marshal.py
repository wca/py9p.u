import py9p

class Marshal(object):
    chatty = 0

    def _splitFmt(self, fmt):
        "Split up a format string."
        idx = 0
        r = []
        while idx < len(fmt):
            if fmt[idx] == '[':
                idx2 = fmt.find("]", idx)
                name = fmt[idx+1:idx2]
                idx = idx2
            else:
                name = fmt[idx]
            r.append(name)
            idx += 1
        return r

    def _prep(self, fmttab):
        "Precompute encode and decode function tables."
        encFunc,decFunc = {},{}
        for n in dir(self):
            if n[:4] == "enc":
                encFunc[n[4:]] = self.__getattribute__(n)
            if n[:4] == "dec":
                decFunc[n[4:]] = self.__getattribute__(n)

        self.msgEncodes,self.msgDecodes = {}, {}
        for k,v in fmttab.items():
            fmts = self._splitFmt(v)
            self.msgEncodes[k] = [encFunc[fmt] for fmt in fmts]
            self.msgDecodes[k] = [decFunc[fmt] for fmt in fmts]

    def setBuf(self, str=""):
        self.bytes = list(str)
    def getBuf(self):
        return "".join(self.bytes)

    def _checkSize(self, v, mask):
        if v != v & mask:
            raise Error("Invalid value %d" % v)
    def _checkLen(self, x, l):
        if len(x) != l:
            raise Error("Wrong length %d, expected %d: %r" % (len(x), l, x))

    def encX(self, x):
        "Encode opaque data"
        self.bytes += list(x)
    def decX(self, l):
        x = "".join(self.bytes[:l])
        #del self.bytes[:l]
        self.bytes[:l] = [] # significant speedup
        return x

    def encC(self, x):
        "Encode a 1-byte character"
        return self.encX(x)
    def decC(self):
        return self.decX(1)

    def enc1(self, x):
        "Encode a 1-byte integer"
        self._checkSize(x, 0xff)
        self.encC(chr(x))
    def dec1(self):
        return long(ord(self.decC()))

    def enc2(self, x):
        "Encode a 2-byte integer"
        self._checkSize(x, 0xffff)
        self.enc1(x & 0xff)
        self.enc1(x >> 8)
    def dec2(self):
        return self.dec1() | (self.dec1() << 8)

    def enc4(self, x):
        "Encode a 4-byte integer"
        self._checkSize(x, 0xffffffffL)
        self.enc2(x & 0xffff)
        self.enc2(x >> 16)
    def dec4(self):
        return self.dec2() | (self.dec2() << 16) 

    def enc8(self, x):
        "Encode a 4-byte integer"
        self._checkSize(x, 0xffffffffffffffffL)
        self.enc4(x & 0xffffffffL)
        self.enc4(x >> 32)
    def dec8(self):
        return self.dec4() | (self.dec4() << 32)

    def encS(self, x):
        "Encode length/data strings with 2-byte length"
        self.enc2(len(x))
        self.encX(x)
    def decS(self):
        return self.decX(self.dec2())

    def encD(self, d):
        "Encode length/data arrays with 4-byte length"
        self.enc4(len(d))
        self.encX(d)
    def decD(self):
        return self.decX(self.dec4())


class Marshal9P(Marshal):
    MAXSIZE = 1024 * 1024            # XXX
    chatty = False

    def __init__(self, dotu=0, chatty=False):
        self.chatty = chatty
        self.dotu = dotu

    def encQ(self, q):
        self.enc1(q.type)
        self.enc4(q.vers)
        self.enc8(q.path)
    def decQ(self):
        return Qid(self.dec1(), self.dec4(), self.dec8())

    def _checkType(self, t):
        if not cmdName.has_key(t):
            raise Error("Invalid message type %d" % t)
    def _checkResid(self):
        if len(self.bytes):
            raise Error("Extra information in message: %r" % self.bytes)

    def send(self, fd, fcall):
        "Format and send a message"
        self.setBuf()
        self._checkType(fcall.type)
        if self.chatty:
            print "-%d->" % fd.fileno(), cmdName[fcall.type], fcall.tag, fcall.tostr()
        self.enc1(fcall.type)
        self.enc2(fcall.tag)
        self.enc(fcall)
        self.enc4(len(self.bytes) + 4)
        self.bytes = self.bytes[-4:] + self.bytes[:-4]
        fd.write(self.getBuf())

    def recv(self, fd):
        "Read and decode a message"
        self.setBuf(fd.read(4))
        size = self.dec4()
        if size > self.MAXSIZE or size < 4:
            raise Error("Bad message size: %d" % size)
        self.setBuf(fd.read(size - 4))
        type,tag = self.dec1(),self.dec2()
        self._checkType(type)
        fcall = Fcall(type, tag)
        self.dec(fcall)
        self._checkResid()
        if self.chatty:
            print "<-%d-" % fd.fileno(), cmdName[type], tag, fcall.tostr()
        return fcall

    def encstat(self, fcall):
        totsz = 0
        for x in fcall.stat:
            if self.dotu:
                totsz = 2+4+13+4+4+4+8+len(x.name)+len(x.uid)+len(x.gid)+len(x.muid)+2+2+2+2+4+4+4
            else:
                totsz = 2+4+13+4+4+4+8+len(x.name)+len(x.uid)+len(x.gid)+len(x.muid)+2+2+2+2
        self.enc2(totsz+2)

        for x in fcall.stat:
            if self.dotu:
                size = 2+4+13+4+4+4+8+len(x.name)+len(x.uid)+len(x.gid)+len(x.muid)+2+2+2+2+4+4+4
            else:
                size = 2+4+13+4+4+4+8+len(x.name)+len(x.uid)+len(x.gid)+len(x.muid)+2+2+2+2
            self.enc2(size)
            self.enc2(x.type)
            self.enc4(x.dev)
            self.encQ(x.qid)
            self.enc4(x.mode)
            self.enc4(x.atime)
            self.enc4(x.mtime)
            self.enc8(x.length)
            self.encS(x.name)
            self.encS(x.uid)
            self.encS(x.gid)
            self.encS(x.muid)
            if self.dotu:
                self.encS(x.uidnum)
                self.encS(x.gidnum)
                self.encS(x.muidnum)

    def enc(self, fcall):
        if fcall.type in (Tversion, Rversion):
            self.enc4(fcall.msize)
            self.encS(fcall.version)
        elif fcall.type == Tauth:
            self.enc4(fcall.afid)
            self.encS(fcall.uname)
            self.encS(fcall.aname)
        elif fcall.type == Rauth:
            self.encQ(fcall.aqid)
        elif fcall.type == Rerror:
            self.encS(fcall.ename)
        elif fcall.type == Tflush:
            self.enc2(fcall.oldtag)
        elif fcall.type == Tattach:
            self.enc4(fcall.fid)
            self.enc4(fcall.afid)
            self.encS(fcall.uname)
            self.encS(fcall.aname)
        elif fcall.type == Rattach:
            self.encQ(fcall.afid)
        elif fcall.type == Twalk:
            self.enc4(fcall.fid)
            self.enc4(fcall.newfid)
            self.enc2(len(fcall.wname))
            for x in fcall.wname:
                self.encS(x)
        elif fcall.type == Rwalk:
            self.enc2(len(fcall.wqid))
            for x in fcall.wqid:
                self.encQ(x)
        elif fcall.type == Topen:
            self.enc4(fcall.fid)
            self.enc1(fcall.mode)
        elif fcall.type in (Ropen, Rcreate):
            self.encQ(fcall.qid)
            self.enc4(fcall.iounit)
        elif fcall.type == Tcreate:
            self.enc4(fcall.fid)
            self.encS(fcall.name)
            self.enc4(fcall.perm)
            self.enc1(fcall.mode)
            if self.dotu:
                self.encS(fcall.extension)
        elif fcall.type == Tread:
            self.enc4(fcall.fid)
            self.enc8(fcall.offset)
            self.enc4(fcall.count)
        elif fcall.type == Rread:
            self.encD(fcall.data)
        elif fcall.type == Twrite:
            self.enc4(fcall.fid)
            self.enc8(fcall.offset)
            self.enc4(len(fcall.data))
            self.encX(fcall.data)
        elif fcall.type == Rwrite:
            self.enc4(fcall.count)
        elif fcall.type in (Tclunk,  Tremove, Tstat):
            self.enc4(fcall.fid)
        elif fcall.type in (Rstat, Twstat):
            if fcall.type == Twstat:
                self.dec4(fcall.fid)
            self.encstat(fcall)


    def decstat(self, fcall, enclen=1):
        fcall.stat = []
        if enclen:
            totsz = self.dec2()
        while len(self.bytes):
            size = self.dec2()
            b = self.bytes
            self.bytes = b[0:size]

            stat = Dir(self.dotu)
            stat.type = self.dec2()     # type
            stat.dev = self.dec4()      # dev
            stat.qid = self.decQ()      # qid
            stat.mode = self.dec4()     # mode
            stat.atime = self.dec4()    # atime
            stat.mtime = self.dec4()    # mtime
            stat.length = self.dec8()   # length
            stat.name = self.decS()     # name  
            stat.uid = self.decS()      # uid
            stat.gid = self.decS()      # gid
            stat.muid = self.decS()     # muid
            if self.dotu:
                stat.uidnum = self.dec4()
                stat.gidnum = self.dec4()
                stat.muidnum = self.dec4()
            fcall.stat.append(stat)
            self.bytes = b
            self.bytes[0:size] = []


    def dec(self, fcall):
        if fcall.type in (Tversion, Rversion):
            fcall.msize = self.dec4()
            fcall.version = self.decS()
        elif fcall.type == Tauth:
            fcall.afid = self.dec4()
            fcall.uname = self.decS()
            fcall.aname = self.decS()
        elif fcall.type == Rauth:
            fcall.aqid = self.decQ()
        elif fcall.type == Rerror:
            fcall.ename = self.decS()
        elif fcall.type == Tflush:
            fcall.oldtag = self.dec2()
        elif fcall.type == Tattach:
            fcall.fid = self.dec4()
            fcall.afid = self.dec4()
            fcall.uname = self.decS()
            fcall.aname = self.decS()
        elif fcall.type == Rattach:
            fcall.afid = self.decQ()
        elif fcall.type == Twalk:
            fcall.fid = self.dec4()
            fcall.newfid = self.dec4()
            l = self.dec2()
            fcall.wname = [self.decS() for n in xrange(l)]
        elif fcall.type == Rwalk:
            l = self.dec2()
            fcall.wqid = [self.decQ() for n in xrange(l)]
        elif fcall.type == Topen:
            fcall.fid = self.dec4()
            fcall.mode = self.dec1()
        elif fcall.type in (Ropen, Rcreate):
            fcall.qid = self.decQ()
            fcall.iounit = self.dec4()
        elif fcall.type == Tcreate:
            fcall.fid = self.dec4()
            fcall.name = self.decS()
            fcall.perm = self.dec4()
            fcall.mode = self.dec1()
            if self.dotu:
                fcall.extension = self.decS()
        elif fcall.type == Tread:
            fcall.fid = self.dec4()
            fcall.offset = self.dec8()
            fcall.count = self.dec4()
        elif fcall.type == Rread:
            fcall.data = self.decD()
        elif fcall.type == Twrite:
            fcall.fid = self.dec4()
            fcall.offset = self.dec8()
            fcall.count = self.dec4()
            fcall.data = self.decX(fcall.count)
        elif fcall.type == Rwrite:
            fcall.count = self.dec4()
        elif fcall.type in (Tclunk, Tremove, Tstat):
            fcall.fid = self.dec4()
        elif fcall.type in (Rstat, Twstat):
            if fcall.type == Twstat:
                fcall.fid = self.dec4()
            self.decstat(fcall)

        return fcall
 
