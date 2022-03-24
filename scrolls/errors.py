import functools
import math
import typing as t

__all__ = (
    "format_positional_error",
    "ScrollError",
    "PositionalError",
    "ParseError",
    "ParseEofError",
    "ParseExpectError",
    "TokenizeError",
    "TokenizeEofError"
)


@functools.lru_cache(128)
def format_positional_error(
    line: int,
    pos: int,
    string: str,
    message: str,
    prior_lines: int = 3
) -> str:
    zfill = max(1, int(math.log10(len(string))))
    lines = [f"{n:0{zfill}} {l}" for n, l in enumerate(string.splitlines())]

    printed_lines = lines[max(0, line - prior_lines): line + 1]

    output_lines = [
        *(["..."] if line - prior_lines >= 1 else []),
        *printed_lines,
        " "*(pos + 1 + zfill) + "^",
        f"line {line}: {message}"
    ]

    return "\n".join(output_lines)


class ScrollError(Exception):
    """Base class for all Scrolls-related errors."""
    pass


class PositionalError(ScrollError):
    """Generic error that happened somewhere in a script.

    Any error in tokenizing, parsing should inherit from this.
    """
    def __init__(
        self,
        line: int,
        pos: int,
        string: str,
        message: str
    ):
        self.line = line
        self.pos = pos
        self.string = string
        self.message = message

    def __str__(self) -> str:
        return format_positional_error(
            self.line,
            self.pos,
            self.string,
            self.message
        )


class TokenizeError(PositionalError):
    pass


class TokenizeEofError(TokenizeError):
    pass


class ParseError(PositionalError):
    def __init__(
        self,
        line: int,
        pos: int,
        string: str,
        message: str
    ):
        super().__init__(
            line,
            pos,
            string,
            message
        )

        self.fatal = False


class ParseEofError(ParseError):
    pass


class ParseExpectError(ParseError):
    pass
