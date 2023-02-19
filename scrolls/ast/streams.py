"""
Character streams for feeding `scrolls.ast.tokenizer.Tokenizer` objects.
"""

import logging
import typing

from . import ast_errors

__all__ = (
    "CharStream",
    "StringStream",
    "REPLStream"
)


logger = logging.getLogger(__name__)


class CharStream(typing.Protocol):
    """
    A character stream. Used as a generic source of characters to tokenize in
    a `scrolls.ast.tokenizer.Tokenizer`.
    """

    def dump_state(self) -> None:
        """
        Prints internal state for debug purposes. Content of the message
        is entirely dependent on the `CharStream` implementation.
        """
        ...

    def current_line(self) -> int:
        """
        Get the line this stream is on. Increments when a newline (`\n`) character
        is encountered.
        """
        ...

    def current_pos(self) -> int:
        """
        Get the character within the current line this stream is on. Resets to 0
        when a new line is encountered.
        """
        ...

    def get_char(self) -> str:
        """
        Get the current character this stream is on.
        """
        ...

    def next_char(self) -> None:
        """
        Advance to the next character.
        """
        ...

    def at_eof(self) -> bool:
        """
        Returns `True` if `CharStream.next_char` just advanced from the last character.
        `CharStream.get_char` should not be called in this state. Since EOF is
        considered a token, at_eof can effectively be considered a virtual character.
        It is always the last one.
        """
        ...

    def after_eof(self) -> bool:
        """
        Returns `True` if `CharStream.next_char` just advanced from the EOF state.
        This is the true end of the stream, after all characters and EOF have been
        streamed.
        """
        ...

    def history(self) -> str:
        """
        Get the history of this stream. Guaranteed to return at least all
        text returned through `CharStream.get_char` and `CharStream.next_char`.

        May return text not yet streamed, depending on the implementation.
        """
        ...


class StringStream(CharStream):
    """
    A `CharStream` that streams an existing string. This is the default implementation
    used by `scrolls.ast.tokenizer.Tokenizer` instances if no stream is specified.
    """
    def __init__(self, string: str):
        self._current_line = 0
        self._current_pos = 0
        self._string = ""
        self._stringlen = 0
        self._more_chars = True

        self.feed(string)
        self._char = 0

    def dump_state(self) -> None:
        print(
            f"current line: {self._current_line}\n"
            f"current pos:  {self._current_pos}\n"
            f"more chars:   {self._more_chars}\n"
        )

    def current_line(self) -> int:
        return self._current_line

    def current_pos(self) -> int:
        return self._current_pos

    def at_eof(self) -> bool:
        off_end = self._char >= self._stringlen

        if off_end and self.after_eof():
            return False

        return off_end

    def get_char(self) -> str:
        if self.after_eof():
            raise ast_errors.StreamEofError("Cannot read from stream stream after EOF.")
        elif self.at_eof():
            raise ast_errors.StreamEofError("Cannot read from string stream at EOF.")

        return self._string[self._char]

    def next_char(self) -> None:
        # If we're at EOF, and try to get the next character, we've
        # exhausted everything.
        if self.at_eof():
            logger.debug("StringStream: set _more_chars False")
            self._more_chars = False
            return

        if self.after_eof():
            raise ast_errors.StreamEofError("Cannot read from string stream after EOF.")

        char = self.get_char()
        if char == "\n":
            self._current_line += 1
            self._current_pos = 0
        else:
            self._current_pos += 1

        self._char += 1

    def after_eof(self) -> bool:
        return not self._more_chars

    def history(self) -> str:
        return self._string

    def feed(self, string: str) -> None:
        """
        Add additional strings to the stream. May be done at any time.
        """
        trimmed_str = string.replace("\r", "")
        self._string += trimmed_str
        self._stringlen += len(trimmed_str)
        self._more_chars = True

        logging.debug(f"StringStream: Fed with \n{string}")


class REPLStream(StringStream):
    """
    A `CharStream` that streams input from stdin. If an EOF is ever encountered,
    instead of entering an EOF state, more input is requested from the user.

    This is done on a per-line basis.
    """
    def __init__(self) -> None:
        super().__init__("")
        self.prefix = ""
        self.set_statement()

    def set_statement(self) -> None:
        """
        Sets the input prefix of the REPL to ">>>". Must be
        called manually on successful execution of a statement.
        """
        self.prefix = ">>> "

    def set_continuation(self) -> None:
        """
        Sets the input prefix of the REPL to "...". Typically, this is
        done automatically.
        """
        self.prefix = "... "

    def consume_line(self) -> None:
        """
        Consume the next line of user input.
        """
        logger.debug("REPLStream: Requesting additional input.")

        # Get new line, ignoring empty lines.
        next_str = ""
        while not next_str.strip():
            next_str = input(self.prefix) + "\n"

        self.feed(next_str)
        self.set_continuation()

    def get_char(self) -> str:
        if self.at_eof():
            logger.debug("REPLStream: get_char: consuming new line")
            self.consume_line()

        return super().get_char()

    def next_char(self) -> None:
        if self.at_eof():
            logger.debug("REPLStream: next_char: consuming new line")
            self.consume_line()

        super().next_char()

    def next_line(self) -> None:
        """
        Skip forward until the next line.
        """
        logger.debug("REPLStream: Skipping current line.")

        # if at EOF, then we're already at a new line, so stream in a new one
        if self.at_eof():
            logger.debug("REPLStream: next_line: consuming new line")
            self.consume_line()
            return

        # Otherwise, skip forward in the current line until we're at a new one.
        # inefficient implementation for now, since this is only needed for
        # errors in the REPL.
        current_line = self.current_line()
        while self.current_line() == current_line:
            self.next_char()
