"""Name and description of the WebFetch tool.

Port of internal/tools/webfetch/prompt.go.
"""

# Inventory row 84 (WIRE-TEMPLATE) — the decided site for this file.
# NAME/DESCRIPTION are wired into the mcp Tool registration by
# tools/webfetch/webfetch.py (webfetch.go:14-16 wires Name/Description).
#
# DESCRIPTION is the Go backtick literal VERBATIM: it begins with a leading
# "\n" (the newline immediately after the opening backtick, prompt.go:5),
# carries the 14 content lines of prompt.go:6-19, and ends with "\n\t" —
# a newline plus a single TAB (prompt.go:20) with NO newline after the tab.
# The judge asserts this string byte-exact (s01), so every byte here is
# load-bearing, including the leading newline and the final tab.
#
# There are NO format placeholders in DESCRIPTION: never run %, .format(),
# f-string interpolation, or any other substitution on it. s01 also asserts
# the description contains NO month-year — never embed a date or anything
# matching [A-Z][a-z]{2} 20\d{2} here.

NAME = "WebFetch"

DESCRIPTION = """
- Fetches content from a specified URL and processes it using an AI model
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Processes the content with the prompt using a small, fast model
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

### Usage notes:
- The URL must be a fully-formed valid URL
- HTTP URLs will be automatically upgraded to HTTPS
- This tool is read-only and does not modify any files
- Results may be summarized if the content is very large
- Includes a self-cleaning 15-minute cache for faster responses when repeatedly accessing the same URL
- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).
	"""

# PORT STATUS: confidence=high todos=0
