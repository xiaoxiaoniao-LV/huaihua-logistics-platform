"""发票/结算凭证 PDF 生成（零第三方依赖）。

PDF 使用预定义中文 CMap（UniGB-UCS2-H）引用系统字体 STSong-Light，不嵌入字库：
Acrobat、WPS、Edge/Chrome 内置阅读器与 macOS 预览都能正常显示中文。
生成结果是单页 A4，可直接作为结算单附件下载或归档。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

_PAGE_W = 595.0
_PAGE_H = 842.0
_MARGIN = 45.0

_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ("", "拾", "佰", "仟")
_GROUP_UNITS = ("", "万", "亿", "兆")


def _hex_text(text: str) -> str:
    """UniGB-UCS2-H 用 UTF-16BE 编码；超出 BMP 的字符直接丢弃。"""
    return text.encode("utf-16-be").hex().upper()


def _text_width(text: str, size: float) -> float:
    """粗略字宽：汉字按 1 em、半角按 0.5 em，用于居中/右对齐。"""
    return sum(size if ord(ch) > 0x2E7F else size * 0.5 for ch in text)


def _text(
    x: float, y: float, size: float, text: str, *,
    align: str = "left", color: tuple[float, float, float] = (0.08, 0.1, 0.14),
) -> str:
    if not text:
        return ""
    if align == "center":
        x -= _text_width(text, size) / 2
    elif align == "right":
        x -= _text_width(text, size)
    r, g, b = color
    return (
        f"BT /F1 {size:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
        f"1 0 0 1 {x:.2f} {y:.2f} Tm <{_hex_text(text)}> Tj ET"
    )


def _line(x1: float, y1: float, x2: float, y2: float, width: float = 0.6) -> str:
    return f"q {width} w 0.72 0.76 0.8 RG {x1} {y1} m {x2} {y2} l S Q"


def _fill(x: float, y: float, w: float, h: float, rgb: tuple[float, float, float]) -> str:
    r, g, b = rgb
    return f"q {r:.3f} {g:.3f} {b:.3f} rg {x} {y} {w} {h} re f Q"


def _money(value: float) -> str:
    return f"¥{value:,.2f}"


def rmb_upper(amount: float | Decimal) -> str:
    """人民币金额转大写，如 1234.56 → 壹仟贰佰叁拾肆元伍角陆分。"""
    cents = int((Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) * 100)
    negative = cents < 0
    cents = abs(cents)
    jiao, fen = (cents // 10) % 10, cents % 10
    yuan = cents // 100

    if yuan == 0:
        integer = ""
    else:
        groups: list[int] = []
        n = yuan
        while n > 0:
            groups.append(n % 10000)
            n //= 10000
        parts: list[str] = []
        for gi in range(len(groups) - 1, -1, -1):
            group = groups[gi]
            if group == 0:
                if parts:
                    parts.append("零")
                continue
            chunk = ""
            need_zero = False
            for pos in range(3, -1, -1):
                digit = (group // (10 ** pos)) % 10
                if digit == 0:
                    need_zero = True
                    continue
                if need_zero and chunk:
                    chunk += "零"
                need_zero = False
                chunk += _DIGITS[digit] + _UNITS[pos]
            parts.append(chunk + _GROUP_UNITS[gi])
        integer = "".join(parts).rstrip("零")

    out = (integer + "元") if integer else ""
    if jiao == 0 and fen == 0:
        out = (out or "零元") + "整"
    else:
        if jiao:
            out += _DIGITS[jiao] + "角"
        elif fen:
            out += "零"
        if fen:
            out += _DIGITS[fen] + "分"
    return ("负" if negative else "") + out


def _content(
    *,
    invoice_no: str,
    issued_at: datetime,
    seller_name: str,
    seller_tax_no: str,
    buyer_name: str,
    buyer_tax_no: str,
    item_name: str,
    note: str,
    amount: float,
    tax_rate: float,
) -> str:
    net = round(amount / (1 + tax_rate), 2) if tax_rate else amount
    tax = round(amount - net, 2)
    x0, x1 = _MARGIN, _PAGE_W - _MARGIN

    parts: list[str] = [
        _text(_PAGE_W / 2, 782, 21, "电子发票", align="center"),
        _text(_PAGE_W / 2, 760, 9.5, "平台服务结算凭证 · 由系统自动开具", align="center",
              color=(0.45, 0.5, 0.56)),
        _line(x0, 746, x1, 746, 1.2),

        # 抬头信息
        _text(x0, 720, 9.5, f"发票号码：{invoice_no}", color=(0.3, 0.35, 0.4)),
        _text(x1, 720, 9.5, f"开票日期：{issued_at:%Y-%m-%d}", align="right",
              color=(0.3, 0.35, 0.4)),

        # 购买方 / 销售方
        _text(x0, 686, 10, "购买方"),
        _text(x0 + 58, 686, 10, f"名称：{buyer_name}"),
        _text(x0 + 330, 686, 10, f"纳税人识别号：{buyer_tax_no or '—'}"),
        _text(x0, 662, 10, "销售方"),
        _text(x0 + 58, 662, 10, f"名称：{seller_name}"),
        _text(x0 + 330, 662, 10, f"纳税人识别号：{seller_tax_no or '—'}"),
        _line(x0, 646, x1, 646),
    ]

    # 明细表
    cols = (x0, x0 + 225, x0 + 270, x0 + 355, x0 + 440, x0 + 475, x1)
    headers = ("项目名称", "数量", "不含税单价", "不含税金额", "税率", "税额")
    aligns = ("left", "center", "right", "right", "center", "right")
    parts.append(_fill(x0, 618, x1 - x0, 24, (0.93, 0.95, 0.97)))
    for i, title in enumerate(headers):
        cx = (cols[i] + cols[i + 1]) / 2 if aligns[i] == "center" else (
            cols[i] + 6 if aligns[i] == "left" else cols[i + 1] - 6
        )
        parts.append(_text(cx, 626, 9.5, title, align=aligns[i]))

    row_y = 592
    values = (item_name, "1", _money(net), _money(net), f"{tax_rate * 100:.0f}%", _money(tax))
    for i, value in enumerate(values):
        cx = (cols[i] + cols[i + 1]) / 2 if aligns[i] == "center" else (
            cols[i] + 6 if aligns[i] == "left" else cols[i + 1] - 6
        )
        parts.append(_text(cx, row_y + 8, 9.5, value, align=aligns[i]))
    parts.extend([_line(x0, row_y, x1, row_y), _line(x0, row_y + 26, x1, row_y + 26)])

    # 合计
    parts.append(_text(x0 + 6, 556, 10, f"价税合计（大写）：{rmb_upper(amount)}"))
    parts.append(_text(x1 - 6, 556, 12, f"（小写）{_money(amount)}", align="right",
                       color=(0.05, 0.32, 0.5)))

    parts.append(_text(x0, 526, 9.5, f"备注：{note}", color=(0.3, 0.35, 0.4)))
    parts.append(_text(x0, 506, 9.5, "开票人：平台运营中心    复核：系统自动校验    收款人：平台结算账户",
                       color=(0.3, 0.35, 0.4)))

    parts.append(_line(x0, 470, x1, 470))
    parts.append(_text(x0, 450, 8.5,
                       "说明：本凭证由平台根据结算单自动生成，税额按现代服务业税率估算；如需税务发票请联系平台运营。",
                       color=(0.5, 0.54, 0.6)))
    return "\n".join(p for p in parts if p)


def _build_pdf(content: str) -> bytes:
    stream = content.encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
            b"/Encoding /UniGB-UCS2-H /DescendantFonts [6 0 R] >>"
        ),
        (
            b"<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 "
            b"/FontBBox [-25 -254 1000 880] /ItalicAngle 0 /Ascent 880 "
            b"/Descent -120 /CapHeight 880 /StemV 80 >>"
        ),
        (
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> "
            b"/FontDescriptor 5 0 R /DW 1000 /W [1 95 500] >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def render_invoice_pdf(
    *,
    invoice_no: str,
    issued_at: datetime,
    seller_name: str,
    seller_tax_no: str,
    buyer_name: str,
    buyer_tax_no: str,
    item_name: str,
    note: str,
    amount: float,
    tax_rate: float,
) -> bytes:
    """生成单页 A4 发票 PDF。"""
    content = _content(
        invoice_no=invoice_no,
        issued_at=issued_at,
        seller_name=seller_name,
        seller_tax_no=seller_tax_no,
        buyer_name=buyer_name,
        buyer_tax_no=buyer_tax_no,
        item_name=item_name,
        note=note,
        amount=float(amount or 0),
        tax_rate=float(tax_rate or 0),
    )
    return _build_pdf(content)
