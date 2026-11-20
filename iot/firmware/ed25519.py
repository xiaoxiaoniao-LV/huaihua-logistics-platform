"""纯 Python Ed25519（MicroPython 兼容）+ OTA 清单规范化。

用途：节点在下载固件前校验清单签名，防止中间人替换版本与哈希。
后端签名见 `backend/app/services/ota_signing.py`，两边的规范化规则必须完全一致：

    {"files":[{"name":"main.py","sha256":"...","size":123}],"version":"3.1.0"}
    —— 键排序、无空格、files 按 name 升序

限制：本实现只追求正确与可移植（ESP32 上一次验签约需数百毫秒），不做常量时间防护；
密钥只保存 32 字节种子/公钥的原始字节，不处理 PEM。
"""

import json

try:
    import hashlib
    _sha512 = hashlib.sha512
except (ImportError, AttributeError):  # 部分固件未编译 sha512，走纯 Python 实现
    _sha512 = None

_MASK64 = (1 << 64) - 1

_K = (
    0x428A2F98D728AE22, 0x7137449123EF65CD, 0xB5C0FBCFEC4D3B2F, 0xE9B5DBA58189DBBC,
    0x3956C25BF348B538, 0x59F111F1B605D019, 0x923F82A4AF194F9B, 0xAB1C5ED5DA6D8118,
    0xD807AA98A3030242, 0x12835B0145706FBE, 0x243185BE4EE4B28C, 0x550C7DC3D5FFB4E2,
    0x72BE5D74F27B896F, 0x80DEB1FE3B1696B1, 0x9BDC06A725C71235, 0xC19BF174CF692694,
    0xE49B69C19EF14AD2, 0xEFBE4786384F25E3, 0x0FC19DC68B8CD5B5, 0x240CA1CC77AC9C65,
    0x2DE92C6F592B0275, 0x4A7484AA6EA6E483, 0x5CB0A9DCBD41FBD4, 0x76F988DA831153B5,
    0x983E5152EE66DFAB, 0xA831C66D2DB43210, 0xB00327C898FB213F, 0xBF597FC7BEEF0EE4,
    0xC6E00BF33DA88FC2, 0xD5A79147930AA725, 0x06CA6351E003826F, 0x142929670A0E6E70,
    0x27B70A8546D22FFC, 0x2E1B21385C26C926, 0x4D2C6DFC5AC42AED, 0x53380D139D95B3DF,
    0x650A73548BAF63DE, 0x766A0ABB3C77B2A8, 0x81C2C92E47EDAEE6, 0x92722C851482353B,
    0xA2BFE8A14CF10364, 0xA81A664BBC423001, 0xC24B8B70D0F89791, 0xC76C51A30654BE30,
    0xD192E819D6EF5218, 0xD69906245565A910, 0xF40E35855771202A, 0x106AA07032BBD1B8,
    0x19A4C116B8D2D0C8, 0x1E376C085141AB53, 0x2748774CDF8EEB99, 0x34B0BCB5E19B48A8,
    0x391C0CB3C5C95A63, 0x4ED8AA4AE3418ACB, 0x5B9CCA4F7763E373, 0x682E6FF3D6B2B8A3,
    0x748F82EE5DEFB2FC, 0x78A5636F43172F60, 0x84C87814A1F0AB72, 0x8CC702081A6439EC,
    0x90BEFFFA23631E28, 0xA4506CEBDE82BDE9, 0xBEF9A3F7B2C67915, 0xC67178F2E372532B,
    0xCA273ECEEA26619C, 0xD186B8C721C0C207, 0xEADA7DD6CDE0EB1E, 0xF57D4F7FEE6ED178,
    0x06F067AA72176FBA, 0x0A637DC5A2C898A6, 0x113F9804BEF90DAE, 0x1B710B35131C471B,
    0x28DB77F523047D84, 0x32CAAB7B40C72493, 0x3C9EBE0A15C9BEBC, 0x431D67C49C100D4C,
    0x4CC5D4BECB3E42B6, 0x597F299CFC657E2A, 0x5FCB6FAB3AD6FAEC, 0x6C44198C4A475817,
)

_H0 = (
    0x6A09E667F3BCC908, 0xBB67AE8584CAA73B, 0x3C6EF372FE94F82B, 0xA54FF53A5F1D36F1,
    0x510E527FADE682D1, 0x9B05688C2B3E6C1F, 0x1F83D9ABFB41BD6B, 0x5BE0CD19137E2179,
)


def _rotr(x, n):
    return ((x >> n) | (x << (64 - n))) & _MASK64


def _sha512_py(data):
    h = list(_H0)
    bits = len(data) * 8
    data = data + b"\x80" + b"\x00" * ((111 - len(data)) % 128) + bits.to_bytes(16, "big")
    for off in range(0, len(data), 128):
        chunk = data[off:off + 128]
        w = [0] * 80
        for i in range(16):
            w[i] = int.from_bytes(chunk[i * 8:i * 8 + 8], "big")
        for i in range(16, 80):
            s0 = _rotr(w[i - 15], 1) ^ _rotr(w[i - 15], 8) ^ (w[i - 15] >> 7)
            s1 = _rotr(w[i - 2], 19) ^ _rotr(w[i - 2], 61) ^ (w[i - 2] >> 6)
            w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & _MASK64
        a, b, c, d, e, f, g, hh = h
        for i in range(80):
            s1 = _rotr(e, 14) ^ _rotr(e, 18) ^ _rotr(e, 41)
            ch = (e & f) ^ ((~e & _MASK64) & g)
            t1 = (hh + s1 + ch + _K[i] + w[i]) & _MASK64
            s0 = _rotr(a, 28) ^ _rotr(a, 34) ^ _rotr(a, 39)
            maj = (a & b) ^ (a & c) ^ (b & c)
            t2 = (s0 + maj) & _MASK64
            hh, g, f, e, d, c, b, a = (
                g, f, e, (d + t1) & _MASK64, c, b, a, (t1 + t2) & _MASK64,
            )
        h = [(x + y) & _MASK64 for x, y in zip(h, (a, b, c, d, e, f, g, hh))]
    return b"".join(x.to_bytes(8, "big") for x in h)


def _hash(data):
    return _sha512(data).digest() if _sha512 else _sha512_py(data)


# ---------------- 曲线运算 ----------------

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * _inv(5) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    d = z1 * 2 * z2 % _P
    e = b - a
    f = d - c
    g = d + c
    h = b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _double(p):
    x1, y1, z1, _ = p
    a = x1 * x1 % _P
    b = y1 * y1 % _P
    c = 2 * z1 * z1 % _P
    h = a + b
    e = h - (x1 + y1) * (x1 + y1)
    g = a - b
    f = c + g
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(p, e):
    """迭代式 double-and-add，避免递归深度限制。"""
    q = (0, 1, 1, 0)
    while e > 0:
        if e & 1:
            q = _add(q, p)
        p = _double(p)
        e >>= 1
    return q


def _encode(p):
    x, y, z, _ = p
    zi = _inv(z)
    x = x * zi % _P
    y = y * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decode(data):
    if len(data) != 32:
        raise ValueError("point length")
    n = int.from_bytes(data, "little")
    y = n & ((1 << 255) - 1)
    if y >= _P:
        raise ValueError("point not canonical")
    x = _xrecover(y)
    if (x & 1) != ((n >> 255) & 1):
        x = _P - x
    p = (x, y, 1, x * y % _P)
    if (y * y - x * x - 1 - _D * x * x % _P * y * y % _P) % _P != 0:
        raise ValueError("point not on curve")
    return p


def _h_int(data):
    return int.from_bytes(_hash(data), "little")


def public_key(seed):
    """由 32 字节种子派生 32 字节公钥。"""
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _hash(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return _encode(_scalarmult(_B, a))


def sign(seed, msg):
    """对 bytes 消息签名，返回 64 字节签名（打包工具使用）。"""
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")
    h = _hash(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    prefix = h[32:]
    pub = _encode(_scalarmult(_B, a))
    r = _h_int(prefix + msg) % _Q
    big_r = _encode(_scalarmult(_B, r))
    s = (r + _h_int(big_r + pub + msg) * a) % _Q
    return big_r + s.to_bytes(32, "little")


def verify(public, signature, msg):
    """校验签名；任何结构异常都返回 False。"""
    try:
        if len(public) != 32 or len(signature) != 64:
            return False
        a = _decode(public)
        r = _decode(signature[:32])
        s = int.from_bytes(signature[32:], "little")
        if s >= _Q:
            return False
        h = _h_int(signature[:32] + public + msg) % _Q
        return _encode(_scalarmult(_B, s)) == _encode(_add(r, _scalarmult(a, h)))
    except Exception:
        return False


# ---------------- 清单规范化（与后端保持一致） ----------------

def canonical_payload(manifest):
    """把清单转为签名载荷字节串：files 按 name 升序，键序固定为 files/version。"""
    files = []
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        files.append((
            str(item.get("name", "")),
            str(item.get("sha256", "")),
            int(item.get("size") or 0),
        ))
    files.sort(key=lambda f: f[0])
    parts = []
    for name, sha, size in files:
        parts.append(
            '{"name":%s,"sha256":%s,"size":%d}'
            % (json.dumps(name), json.dumps(sha), size)
        )
    text = '{"files":[%s],"version":%s}' % (
        ",".join(parts), json.dumps(str(manifest.get("version", "")))
    )
    return text.encode("utf-8")
