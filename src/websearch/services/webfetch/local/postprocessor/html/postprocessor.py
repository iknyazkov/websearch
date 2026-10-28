"""HTML postprocessor: extract the relevant text from fetched HTML bytes.

Port of internal/services/webfetch/local/postprocessor/html/postprocessor.go.

The charset step mirrors x/net/html/charset (DetermineEncoding + NewReader,
x/net@v0.58.0) bug-for-bug — see inventory row 49 / conflicts.md C-1: the
declared Content-Type parameter NEVER reaches the decoder because Handle
hardcodes ``"text/html"`` (postprocessor.go:29), so decoding is decided by
x/net's DetermineEncoding on the raw body bytes alone.
"""

import codecs
from collections.abc import Iterator
from html import (
    unescape as html_unescape,
)  # stdlib html (§4 absolute import), mirrors Go's html.UnescapeString

from bs4 import BeautifulSoup, Tag

from websearch.services.webfetch.local.postprocessor import postprocessor

min_text_len = 20
min_code_len = 10
min_inline_code = 5
min_content_len = 200
min_child_count = 2


class HTMLPostprocessor:
    def handle(self, data: bytes, parameters: dict[str, str]) -> str:
        try:
            return extract_relevant_text(data, "text/html")
        except Exception:  # noqa: BLE001
            # SAFETY: Go's Handle swallows EVERY extractor error into
            # postprocessor.ContentWasNotFound ("" — postprocessor.go:9 has no
            # distinct sentinel). The broad except is the faithful mirror of
            # `if err != nil { return postprocessor.ContentWasNotFound }`
            # (postprocessor.go:30-32); narrowing it would leak
            # extract_relevant_text's ValueError contract through the
            # Postprocessor boundary where Go never leaks an error.
            return postprocessor.ContentWasNotFound


# Private methods


def extract_relevant_text(data: bytes, content_type: str) -> str:
    """Mirror of extractRelevantText (postprocessor.go:39-115).

    Raises on failure; the three messages are byte-exact and unit-test-visible
    but never escape Handle (inventory row 47 / NIL-SWALLOW).
    """
    try:
        label = _determine_encoding(data, content_type)
        text = _decode(data, label)
    except Exception as cause:
        raise ValueError("charset detection: " + str(cause)) from cause

    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception as cause:
        raise ValueError("parse HTML: " + str(cause)) from cause

    clean_document(soup)
    main_content = find_main_content(soup)

    parts: list[str] = []
    # Go dedupes via hashText's FNV-64a of the raw text (postprocessor.go:169-173);
    # the hash never escapes the function, so the port keys the set by the raw
    # string itself — strictly more precise, zero observable difference (row 52).
    seen: set[str] = set()

    titles = soup.select("title")
    title = "".join(t.get_text() for t in titles).strip()
    if title != "":
        parts.append("# " + title + "\n\n")

    meta = soup.find("meta", attrs={"name": "description"})
    if isinstance(meta, Tag):
        desc_attr = meta.get("content", "")
        if isinstance(desc_attr, str):
            desc = desc_attr.strip()
            if desc != "":
                parts.append("> " + desc + "\n\n")

    for el in main_content.select("h1,h2,h3,h4,p,li,blockquote,pre,code"):
        node = el.name
        # UNESCAPE BEFORE TRIM, mirroring postprocessor.go:68
        # (TrimSpace(html.UnescapeString(...))); the order is load-bearing
        # (row 50/53). Go len() is BYTE length — every threshold below
        # compares len(raw.encode("utf-8")), never len(raw) (row 54).
        raw = html_unescape(el.get_text()).strip()
        raw_len = len(raw.encode("utf-8"))

        if node in ("pre", "code"):
            if raw_len >= min_code_len:
                if raw in seen:
                    continue
                seen.add(raw)

                if raw_len >= min_inline_code and node == "code":
                    parts.append("`" + raw + "`")
                else:
                    parts.append("```\n" + raw + "\n```\n\n")

        elif node.startswith("h"):
            # Go: map lookup on an absent key yields "" (nil-map zero value) —
            # .get(node, "") mirrors it for h5/h6 (unreachable via the selector
            # but kept bug-for-bug, postprocessor.go:87).
            level = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}.get(node, "")
            if raw_len > 0:
                if raw in seen:
                    continue
                seen.add(raw)
                parts.append(level + " " + raw + "\n\n")

        else:
            if raw_len < min_text_len or raw.startswith("Read more"):
                continue
            if raw in seen:
                continue
            seen.add(raw)
            parts.append(raw + "\n\n")

    result = "".join(parts).strip()
    if len(result.encode("utf-8")) == 0:
        raise ValueError("no content found")
    return result


def clean_document(soup: BeautifulSoup) -> None:
    """Two removal passes, selector lists VERBATIM (postprocessor.go:117-132, row 48)."""
    for el in soup.select(
        """
		script, style, noscript, iframe,
		[class*="google-ad"], [class*="googlesyndication"],
		[class*="adsbygoogle"], .ad, .ads, .advertisement,
		.advert, .banner-ad, .sponsored, .sponsor,
		[id*="ad-"], [class*="ad-"], [id*="advert"],
		[class*="sidebar"], .sidebar-ad,
		nav, footer, header, aside,
		.cookie-notice, [id*="cookie"], .cookie-banner,
		.social-links, .social-share, [class*="social-share"],
		[class*="popup"], .modal:not([role="dialog"])
	"""
    ):
        el.decompose()

    for el in soup.select('[data-ad], [data-adunit], [aria-label*="ad"]'):
        el.decompose()


def find_main_content(soup: BeautifulSoup) -> Tag:
    """Mirror of findMainContent (postprocessor.go:134-167)."""
    priority = [
        "article#content, article#post",
        "main, #main",
        ".post-content, .entry-content, .article-body",
        "#content, .main-content",
        ".readme, #readme",
        "[role='main']",
    ]

    for sel in priority:
        found = soup.select(sel)
        if found:
            return found[0]

    # Go's html.Parse ALWAYS synthesizes <body>; bs4 + html.parser does NOT
    # (soup.body is None for '', 'hello world', '<p>x</p>' — probed). The soup
    # OBJECT is the prescribed stand-in for both the best-div scan and the
    # final fallback (row 51, pinned per A-12).
    # TODO(port): body-less documents diverge from Go's synthesized body —
    # a whole-document root narrows best-div to one child where the soup
    # stand-in emits both divs' content; branch is Go-unreachable, kept.
    root = soup.body if soup.body is not None else soup

    best: Tag | None = None
    best_len = 0

    for el in root.select("div, section, article"):
        # Byte length (row 51/54): len(strings.TrimSpace(s.Text())) in Go.
        text_len = len(el.get_text().strip().encode("utf-8"))
        child_count = len(el.select("p, h1, h2, h3"))
        # Strictly greater keeps the FIRST max (Go uses >, not >=).
        if (
            text_len > min_content_len
            and child_count > min_child_count
            and text_len > best_len
        ):
            best_len = text_len
            best = el

    if best is not None:
        return best

    return root


def new() -> HTMLPostprocessor:
    return HTMLPostprocessor()


# Charset detection — mirror of x/net/html/charset DetermineEncoding restricted
# to the hardcoded input (row 49 / conflicts.md C-1). Go also consults
# params["charset"] of the Content-Type here (charset.go:66-71), but
# mime.ParseMediaType("text/html") carries no charset param, so that branch is
# inert for this call site and omitted.

_BOMS = (
    (b"\xfe\xff", "utf-16be"),
    (b"\xff\xfe", "utf-16le"),
    (b"\xef\xbb\xbf", "utf-8"),
)

# x/net's raw-text element set (token.go:843-861, startTagIn switch): a start
# tag for any of these swallows subsequent markup until its end tag, so metas
# inside are unreachable to the prescan. plaintext has NO end tag — Text()
# reads it to EOF (token.go:1042-1048), so a plaintext start tag ENDS the
# prescan (row 49; token.go:849/1042-1055).
_RAW_TEXT_TAGS = frozenset(
    {
        "script",
        "style",
        "textarea",
        "title",
        "iframe",
        "noembed",
        "noframes",
        "noscript",
        "xmp",
        "plaintext",
    }
)


def _determine_encoding(data: bytes, content_type: str) -> str:
    """Mirror of x/net DetermineEncoding (charset.go:52-104); returns the codec label."""
    del content_type  # never reaches the decoder in Go either (postprocessor.go:29)

    content = data[:1024]

    for bom, enc in _BOMS:
        if content.startswith(bom):
            return enc

    if len(content) > 0:
        label = _prescan(content)
        if label is not None:
            return label

    # Try to detect UTF-8. First eliminate any partial rune at the end — the
    # cut is at the FIRST RuneStart scanning back at most 3 bytes with NO
    # completeness check (charset.go:80-90): a COMPLETE trailing 2/3-byte rune
    # IS cut. Bug-for-bug per row 49 (12/12 probe parity).
    for i in range(len(content) - 1, max(len(content) - 4, -1), -1):
        b = content[i]
        if b < 0x80:
            break
        if b & 0xC0 != 0x80:  # utf8.RuneStart
            content = content[:i]
            break
    has_high_bit = any(b >= 0x80 for b in content)
    if has_high_bit:
        try:
            content.decode("utf-8")  # utf8.Valid
        except UnicodeDecodeError:
            pass
        else:
            return "utf-8"

    return "windows-1252"


def _decode(data: bytes, label: str) -> str:
    """errors="replace" everywhere; UTF-16 via codecs + strip leading U+FEFF (row 49)."""
    text = data.decode(label, errors="replace")
    if label in ("utf-16le", "utf-16be") and text.startswith("\ufeff"):
        text = text[1:]
    return text


def _lookup(label: str) -> str | None:
    """Mirror of charset.Lookup (htmlindex.Get membership).

    Returns the INPUT label on success — NOT codecs.lookup(label).name: the
    canonical name breaks downstream spellings like 'utf-16le' (row 49c).
    """
    normalized = label.strip().lower()  # htmlindex.Get: ToLower(TrimSpace(name))
    try:
        codecs.lookup(normalized)
    except LookupError:
        # A Lookup failure does NOT abort the prescan (charset.go:194-209):
        # the caller keeps scanning the next tag (row 49 / A-9a).
        return None
    # TODO(port): the WHATWG label table is a superset of Python codecs
    # aliases — a WHATWG-only label (Go decodes) misses here and the scan
    # falls through to the heuristic; conversely a label Python accepts but
    # WHATWG rejects (e.g. 'iso-8859-1', which WHATWG remaps to
    # windows-1252) decodes differently. Unreachable in the fixtures.
    return normalized


def _from_meta_element(s: str) -> str:
    """Mirror of fromMetaElement (charset.go:213-243); s arrives lowercased."""
    while s != "":
        cs = s.find("charset")
        if cs == -1:
            return ""
        s = s[cs + len("charset") :]
        s = s.lstrip(" \t\n\f\r")
        if not s.startswith("="):
            continue
        s = s[1:]
        s = s.lstrip(" \t\n\f\r")
        if s == "":
            return ""
        q = s[0]
        if q == '"' or q == "'":
            s = s[1:]
            close_quote = s.find(
                q
            )  # strings.IndexRune(s, rune(q)) — single-char find is equivalent
            if close_quote == -1:
                return ""
            return s[:close_quote]
        end = -1
        for i, ch in enumerate(s):
            if ch in "; \t\n\f\r":
                end = i
                break
        if end == -1:
            end = len(s)
        return s[:end]
    return ""


def _prescan(content: bytes) -> str | None:
    """Mirror of prescan (charset.go:155-211) over a tokenizer-shaped scan (A-9b)."""
    for name, attrs in _iter_start_tags(content):
        if name != "meta":
            continue

        got_pragma = False
        # dontKnow=0, doNeedPragma=1, doNotNeedPragma=2 (charset.go:165-171)
        need_pragma = 0
        resolved: str | None = None

        for key, val_bytes in attrs:
            # Go lowercases attribute VALUES in-place before use
            # (charset.go:168-174); bytes.lower() is ASCII-only, byte-exact.
            val = val_bytes.lower().decode("latin-1")

            if key == "http-equiv":
                if val == "content-type":
                    got_pragma = True

            elif key == "content":
                if resolved is None:
                    label = _from_meta_element(val)
                    if label != "":
                        looked = _lookup(label)
                        if looked is not None:
                            resolved = looked
                            need_pragma = 1

            elif key == "charset":
                resolved = _lookup(val)
                need_pragma = 2

        if need_pragma == 0 or (need_pragma == 1 and not got_pragma):
            continue

        if resolved is not None:
            if resolved.startswith("utf-16"):
                # TODO(port): utf-16-prefix label remap (charset.go:205-208):
                # a meta-declared utf-16 label decodes as utf-8 in Go
                # (e=Nop). Implemented faithfully but unreachable in the
                # fixtures — unpinned by probes.
                resolved = "utf-8"
            return resolved

    return None


def _iter_start_tags(content: bytes) -> Iterator[tuple[str, list[tuple[str, bytes]]]]:
    """Tokenizer-shaped reachability scan (x/net/html token.go, A-9b).

    Yields (lowercased tag name, attrs) for every start tag the x/net
    tokenizer would emit, in document order. Raw-text elements swallow their
    content (no tags inside); markup declarations, comments, end tags and
    bogus comments are skipped; a truncated tag ends the scan (ErrorToken).
    Attribute values are RAW (not lowercased) — charset.go's prescan
    lowercases them itself; first occurrence of a duplicate key wins.
    """
    n = len(content)
    i = 0
    while True:
        lt = content.find(b"<", i)
        if lt == -1:
            return
        j = lt + 1
        if j >= n:
            return  # '<' at EOF: text, then ErrorToken
        c = content[j : j + 1]

        if c == b"!":
            if content.startswith(b"<!--", lt):
                end = content.find(b"-->", lt + 4)
                if end == -1:
                    return  # unterminated comment
                i = end + 3
            else:  # doctype / other markup declaration: skip to '>'
                gt = content.find(b">", j)
                if gt == -1:
                    return
                i = gt + 1
            continue

        if c == b"/" or c == b"?":  # end tag / bogus comment: skip to '>'
            gt = content.find(b">", j)
            if gt == -1:
                return
            i = gt + 1
            continue

        if not (b"a" <= c <= b"z" or b"A" <= c <= b"Z"):
            i = j  # '<' not followed by [A-Za-z] is text (tag-open state)
            continue

        # Start tag: read the tag name (readTagName).
        k = j
        while k < n and content[k : k + 1] not in (
            b" ",
            b"\t",
            b"\n",
            b"\r",
            b"\f",
            b"/",
            b">",
        ):
            k += 1
        name = content[j:k].lower().decode("latin-1")

        # Attribute loop (readTag/readTagAttrKey/readTagAttrVal).
        attrs: list[tuple[str, bytes]] = []
        seen_keys: set[str] = set()
        i = k
        terminated = False
        while i < n:
            while i < n and content[i] in b" \t\n\r\f":
                i += 1
            if i >= n:
                break
            if content[i : i + 1] == b">":
                i += 1
                terminated = True
                break

            # Attribute key.
            ks = i
            while i < n:
                ch = content[i : i + 1]
                if ch == b"=":
                    if ks == i:
                        i += 1  # '=' before the name begins: part of the key (WHATWG 13.2.5.32)
                        continue
                    break
                if ch in (b" ", b"\t", b"\n", b"\r", b"\f", b"/", b">"):
                    break
                i += 1
            key = content[ks:i].lower().decode("latin-1")

            # Attribute value.
            val = b""
            have_val = False
            while i < n and content[i] in b" \t\n\r\f":
                i += 1
            if i < n and content[i : i + 1] == b"/":
                # Self-closing start tag state: no value ('/' consumed, WHATWG 13.2.5.34).
                i += 1
            elif i < n and content[i : i + 1] != b"=":
                pass  # no value; the char is reconsumed
            else:
                i += 1  # consume '='
                while i < n and content[i] in b" \t\n\r\f":
                    i += 1
                if i >= n:
                    break
                quote = content[i : i + 1]
                if quote == b">":
                    pass  # no value; '>' reconsumed
                elif quote in (b'"', b"'"):
                    i += 1
                    endq = content.find(quote, i)
                    if endq == -1:
                        val = content[i:]
                        have_val = True
                        i = n
                    else:
                        val = content[i:endq]
                        have_val = True
                        i = endq + 1
                else:
                    vstart = i
                    while i < n and content[i : i + 1] not in (
                        b" ",
                        b"\t",
                        b"\n",
                        b"\r",
                        b"\f",
                        b">",
                    ):
                        i += 1
                    val = content[vstart:i]
                    have_val = True

            if key != "" and key not in seen_keys:
                # First occurrence of a duplicate key wins (readTag).
                seen_keys.add(key)
                if have_val:
                    attrs.append((key, val))
                else:
                    attrs.append((key, b""))

        if not terminated:
            return  # truncated tag: ErrorToken

        yield name, attrs

        if name in _RAW_TEXT_TAGS:
            if name == "plaintext":
                return  # plaintext consumes the rest of the input
            nxt = _skip_raw_text(content, i, name)
            if nxt is None:
                return
            i = nxt


def _skip_raw_text(content: bytes, i: int, tag: str) -> int | None:
    """Mirror of readRawOrRCDATA/readRawEndTag: skip to just past the matching
    ``</tag`` end tag (case-insensitive, followed by a delimiter byte); None if
    the input ends inside the raw text."""
    tag_bytes = tag.encode("ascii")
    n = len(content)
    while True:
        k = content.find(b"</", i)
        if k == -1:
            return None
        after = k + 2
        if content[after : after + len(tag_bytes)].lower() != tag_bytes:
            i = after
            continue
        pos = after + len(tag_bytes)
        if pos >= n:
            return None
        if content[pos] in b" \t\n\r\f/>":
            gt = content.find(b">", pos)
            if gt == -1:
                return None
            return gt + 1
        i = after


# PORT STATUS: confidence=high todos=3
