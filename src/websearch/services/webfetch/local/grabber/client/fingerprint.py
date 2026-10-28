"""Grabber client fingerprint (Go: client/fingerprint.go)."""

# Row 21: Go's enum shape (``type Fingerprint string`` + ``Value()`` at
# fingerprint.go:7-11) exists only to namespace the constant; the alias makes
# ``string(fingerprint)`` at :10 a no-op, so no ``.value()`` method is ported
# (a method on str would be noise). The conservative str-subclass alternative
# is recorded in the row; nothing consumes it.
Fingerprint = str

# FF-4 (rulebook §0 FIX-FORWARD, inventory row 21): the Go constant carried a
# stale Chrome/91 UA string; the port pins this real Firefox UA literal
# byte-exact. The old Chrome/91 value is deliberately NOT ported.
FIREFOX_UA: Fingerprint = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:158.0) Gecko/20100101 Firefox/158.0"


def get_fingerprint() -> str:
    # Row 21 homes Go's getFingerprint() (grabber.go:51-52, ``return
    # Firefox.Value()``) here with the constant. Sole consumer: the client
    # grabber's User-Agent header (row 25); the github grabber reads
    # FIREFOX_UA directly (github/grabber.go:74 ``client.Firefox.Value()``).
    return FIREFOX_UA


# PORT STATUS: confidence=high todos=0
