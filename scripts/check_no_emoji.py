import re
import sys
from pathlib import Path

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U00002600-\U000027bf"
    "\U00002b00-\U00002bff"
    "\U0000fe0f"
    "\U0000200d"
    "]"
)

EXCLUDED_PREFIXES = ("docs/",)


def find_emoji(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return []
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if EMOJI_PATTERN.search(line)
    ]


def main(argv: list[str]) -> int:
    failed = False
    for name in argv:
        if name.replace("\\", "/").startswith(EXCLUDED_PREFIXES):
            continue
        for number, line in find_emoji(Path(name)):
            sys.stderr.write(f"{name}:{number}: emoji found: {line}\n")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
