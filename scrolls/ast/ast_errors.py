"""
Errors related to language parsing.
"""

from .. import errors as base_errors

__all__ = (
    "StreamError",
    "StreamEofError",
    "TokenizeError",
    "TokenizeEofError",
    "ParseError",
    "ParseEofError",
    "ParseExpectError"
)


class StreamError(base_errors.ScrollError):
    pass


class StreamEofError(StreamError):
    pass


class TokenizeError(base_errors.PositionalError):
    """Generic error raised while lexing/tokenizing a script."""
    pass


class TokenizeEofError(TokenizeError):
    """Raised when the lexer/tokenizer hits an unexpected EOF (end of script)."""
    pass


class ParseError(base_errors.PositionalError):
    """Generic error raised during the parsing stage."""
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

        # IMPLEMENTATION DETAIL
        # Sets whether this parse error is fatal or not. Defaults to `False`.
        # If `True`, a `ParseError` will cause all parsing to stop immediately and
        # raise the error. If `fatal`  is `False`, a parse function may try alternative
        # parsing. Internally, `fatal = False` is used by `parse_choice` to determine
        # which parsing function to choose. See `scrolls.ast` for more details.
        self.fatal = False


class ParseEofError(ParseError):
    """Raised when an EOF is encountered too early while parsing a script."""
    pass


class ParseExpectError(ParseError):
    """Raised when an unexpected token is encountered during parsing."""
    pass
