"""Choice postprocessor: dispatch on the response's media type.

Port of internal/services/webfetch/local/postprocessor/choice/processor.go.

The dispatch is the FF-6 fixed form (rulebook §0, inventory row 45): Go's
exact-match switch on the raw ``parameters.Get("Content-Type")`` string is
replaced by a media-type parse — split before ``;``, strip, lowercase — so
``text/html; charset=windows-1251`` reaches the html extractor. The plain
branch does NO charset detection of any kind (conflicts.md C-12): raw bytes
to text via utf-8 ``errors="replace"``, mirroring Go's ``string(rawBytes)``.
"""

from websearch.services.webfetch.local.postprocessor import postprocessor
from websearch.services.webfetch.local.postprocessor.html.postprocessor import (
    HTMLPostprocessor,
)

# Go const block (processor.go:11-15).
html_content_type = "text/html"
plain_text_content_type = "text/plain"
json_content_type = "application/json"


class ChoicePostprocessor:
    """Go struct ``ChoicePostprocessor{htmlPostProcessor *html.HTMLPostprocessor}``.

    The one field is always set by the constructor (the only constructor is
    new(), service.go:27), so it is non-Optional here — same shape as the
    sibling ClientGrabber field judgment (§2's Optional+assert shape is for
    fields that can be nil after zero-value construction; this one cannot).
    """

    def __init__(self, html_post_processor: HTMLPostprocessor) -> None:
        self.html_post_processor = html_post_processor

    def handle(self, data: bytes, parameters: dict[str, str]) -> str:
        # Go processor.go:22 — parameters.Get("Content-Type") canonicalizes
        # MIME case on lookup; the pinned port convention (FF-5/FF-6 rows)
        # lowercases every key at the grabber boundary, so the lookup key is
        # the lowercase "content-type". A case-sensitive .get("Content-Type")
        # is NOT equivalent and is forbidden by row 45.
        raw = parameters.get("content-type", "")
        # FF-6 (row 45): media-type parse — split before ';', strip, lower.
        media = raw.split(";", 1)[0].strip().lower()

        if media == html_content_type:
            return self.html_post_processor.handle(data, parameters)
        if media == plain_text_content_type:
            # Go processor.go:26-31 is io.ReadAll + string(rawBytes) with NO
            # charset detection. The io.ReadAll error branch (processor.go:28-30
            # -> ContentWasNotFound) EVAPORATES in the port: Result carries
            # data: bytes (FF-5), so there is no reader and no read error to
            # map — row 46 sanctions deleting the branch, not porting a dead
            # try/except. Plain branch: bytes straight to text.
            # TODO(port): Go string(bytes) keeps invalid bytes and the mcp
            # SDK's JSON marshal replaces EACH invalid byte with U+FFFD,
            # while Python's errors="replace" emits one U+FFFD per maximal
            # bad subsequence — differs only on invalid-UTF-8 plaintext;
            # valid UTF-8 (all fixtures) is identical (row 45).
            return data.decode("utf-8", errors="replace")
        if media == json_content_type:
            # Go processor.go:32-33 — explicit case, kept for structural
            # parity with the switch even though it returns the same value
            # as the fall-through below.
            return postprocessor.ContentWasNotFound

        # Go processor.go:36 — the switch's implicit default.
        return postprocessor.ContentWasNotFound


# Initialization


def new(html_post_processor: HTMLPostprocessor) -> postprocessor.Postprocessor:
    # Go processor.go:41-43 — constructor return type is the Postprocessor
    # interface (Protocol here); satisfaction stays structural.
    return ChoicePostprocessor(html_post_processor=html_post_processor)


# PORT STATUS: confidence=high todos=1
