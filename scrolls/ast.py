import dataclasses
import enum
import json
import logging
import types
import typing as t

from . import errors

__all__ = (
    "AST",
    "ASTNode",
    "ASTNodeType",
    "ASTStateError",
    "ParseContext",
    "Token",
    "Tokenizer",
    "TokenType",
    "parse_scroll"
)

logger = logging.getLogger(__name__)

ParserT = t.Callable[['ParseContext'], 'ASTNode']

EOF = ""
COMMAND_SEP = [";", "\n"]
BLOCK_OPEN = "{"
BLOCK_CLOSE = "}"
OPEN_PAREN = "("
CLOSE_PAREN = ")"
CONTROL_SIGIL = "!"
EXPANSION_SIGIL = "$"
MULTI_SIGIL = "^"


class TokenType(enum.Enum):
    OPEN_PAREN = 1
    CLOSE_PAREN = 2
    OPEN_BLOCK = 3
    CLOSE_BLOCK = 4
    EXPANSION_SIGIL = 5
    MULTI_SIGIL = 6
    CONTROL_SIGIL = 7
    COMMAND_SEP = 8
    STRING_LITERAL = 9
    EOF = 10
    WHITESPACE = 11


class TokenizeConsumeRestState(enum.Enum):
    OFF = 0
    COUNTING = 1
    CONSUME = 2


class ASTNodeType(enum.Enum):
    NONE = 0
    EOF = 1
    ROOT = 2
    STRING = 3
    COMMAND_CALL = 4
    COMMAND_ARGUMENTS = 5
    BLOCK = 6
    CONTROL_CALL = 7
    CONTROL_ARGUMENTS = 8
    EXPANSION = 9
    EXPANSION_SINGLE = 10
    EXPANSION_MULTI = 11
    EXPANSION_VAR = 12
    EXPANSION_CALL = 13
    EXPANSION_ARGUMENTS = 14


# TODO: Add slots=True for python 3.10
@dataclasses.dataclass
class Token:
    type: TokenType
    value: str
    line: int
    position: int
    consume_rest: bool = False

    def __str__(self) -> str:
        return f"{self.type.name}:{repr(self.value)}"


class AST:
    def __init__(self, root: 'ASTNode', script: str):
        self.root: ASTNode = root
        self.script: str = script

    def prettify(self) -> str:
        return self.root.prettify()

    def __repr__(self) -> str:
        return f"ScrollAST({repr(self.root)}"


class ASTStateError(errors.ScrollError):
    """Generic tokenizer/parser that includes an entire AST node.

    Raised by ASTNode functions on invalid state.

    Generally internal to the scrolls module. If one of these errors makes it out,
    something is probably wrong.
    """
    def __init__(self, node: 'ASTNode', message: str):
        self.node = node
        self.message = message

    def __str__(self) -> str:
        return self.message


class ASTNode:
    __slots__ = (
        "children",
        "type",
        "_tok"
    )

    def __init__(self, type: ASTNodeType, token: t.Optional[Token]):
        self.children: t.MutableSequence['ASTNode'] = []
        self.type = type

        # For string tokens, this will be
        self._tok: t.Optional[Token] = token

    def to_dict(self) -> t.Mapping[str, t.Any]:
        mapping = {
            "_type": self.type.name,
            "_tok": str(self._tok),
            "children": [child.to_dict() for child in self.children]
        }

        return mapping

    def prettify(self) -> str:
        s = json.dumps(self.to_dict(), sort_keys=True, indent=4)
        return s

    @property
    def tok(self) -> Token:
        if self._tok is None:
            raise ASTStateError(self, "cannot get token, is None")

        return self._tok

    @tok.setter
    def tok(self, token: Token) -> None:
        self._tok = token

    def has_token(self) -> bool:
        return self._tok is not None

    def wrap(self, node_type: ASTNodeType, as_child: bool = False) -> 'ASTNode':
        new_node = ASTNode(
            node_type,
            self.tok
        )

        if as_child:
            new_node.children.append(self)

        return new_node

    def str_content(self) -> str:
        if self.type != ASTNodeType.STRING:
            raise ASTStateError(self, "str_content requires STRING type node")

        assert self._tok is not None
        return self._tok.value

    def find_all(self, func: t.Callable[['ASTNode'], bool]) -> t.Sequence['ASTNode']:
        found = []

        if func(self):
            found.append(self)

        for child in self.children:
            found.extend(child.find_all(func))

        return found

    def __str__(self) -> str:
        return repr(self)

    def __repr__(self) -> str:
        if self.type is ASTNodeType.STRING:
            return f"ScrollASTNode({self.type.name}, '{str(self._tok)}')"
        else:
            return f"ScrollASTNode({self.type.name}, {repr(self.children)})"


class Tokenizer:
    def __init__(
        self,
        string: str,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ):
        self.current_line = 0
        self.current_pos = 0
        self.string = string.replace("\r", "").strip()
        self.stringlen = len(self.string)
        self.char = 0
        self.consume_rest_triggers = consume_rest_triggers
        self.consume_rest_state = TokenizeConsumeRestState.OFF
        self.consume_rest_count = 0
        self.previous_token_was_sep = True
        self.whitespace = "\t "

        # Map of single characters to token types
        self.charmap = {
            "\n": TokenType.COMMAND_SEP,
            ";": TokenType.COMMAND_SEP,
            OPEN_PAREN: TokenType.OPEN_PAREN,
            CLOSE_PAREN: TokenType.CLOSE_PAREN,
            BLOCK_OPEN: TokenType.OPEN_BLOCK,
            BLOCK_CLOSE: TokenType.CLOSE_BLOCK,
            EXPANSION_SIGIL: TokenType.EXPANSION_SIGIL,
            CONTROL_SIGIL: TokenType.CONTROL_SIGIL,
            MULTI_SIGIL: TokenType.MULTI_SIGIL
        }

        self.string_literal_stop = "".join([key for key in self.charmap]) + self.whitespace

        self.consume_rest_stop: t.Sequence[str] = []
        self.single_char_token_enable = True
        self.set_consume_rest_all(False)
        self.set_single_char_token_enable(True)

    def set_consume_rest_all(self, consume_all: bool) -> None:
        if not consume_all:
            self.consume_rest_stop = [
                "\n", ";", BLOCK_OPEN, BLOCK_CLOSE
            ]
        else:
            self.consume_rest_stop = []

    def set_single_char_token_enable(self, en: bool) -> None:
        self.single_char_token_enable = en

        if en:
            self.string_literal_stop = "".join([key for key in self.charmap]) + self.whitespace
        else:
            self.string_literal_stop = self.whitespace

    def error(self, err_type: t.Type[errors.PositionalError], message: str) -> t.NoReturn:
        raise err_type(
            self.current_line,
            self.current_pos,
            self.string,
            message
        )

    def at_eof(self) -> bool:
        return self.char >= self.stringlen

    def get_char(self) -> str:
        return self.string[self.char]

    def next_char(self) -> None:
        char = self.get_char()
        if char == "\n":
            self.current_line += 1
            self.current_pos = 0
        else:
            self.current_pos += 1

        self.char += 1

    # Get a single char token.
    def accept_single_char(self) -> t.Optional[Token]:
        if not self.single_char_token_enable:
            return None

        char = self.get_char()

        if char in self.charmap:
            tok = Token(
                self.charmap[char],
                char,
                self.current_line,
                self.current_pos
            )
            self.next_char()
            return tok

        return None

    def accept_eof(self) -> t.Optional[Token]:
        if self.at_eof():
            return Token(
                TokenType.EOF,
                EOF,
                self.current_line,
                self.current_pos
            )
        else:
            return None

    def accept_whitespace(self) -> t.Optional[Token]:
        char = self.get_char()
        if char in self.whitespace:
            self.next_char()
            return Token(
                TokenType.WHITESPACE,
                char,
                self.current_line,
                self.current_pos
            )

        return None

    def accept_string_literal(
        self,
        stop_chars: t.Sequence[str] = (),
        error_on_eof: bool = False
    ) -> t.Optional[Token]:
        if self.at_eof():
            self.error(
                errors.TokenizeEofError,
                "String literal should not start on EOF"
            )

        char = self.get_char()
        pos = self.current_pos
        line = self.current_line
        chars = []

        while char not in stop_chars:
            chars.append(char)
            self.next_char()
            if self.at_eof():
                if error_on_eof:
                    self.error(
                        errors.TokenizeEofError,
                        "Unexpected EOF while parsing string literal."
                    )
                else:
                    break

            char = self.get_char()

        return Token(
            TokenType.STRING_LITERAL,
            "".join(chars),
            line,
            pos
        )

    # Accepts a normal string literal. No CONSUME_REST, not quoted.
    def accept_string_literal_normal(self) -> t.Optional[Token]:
        return self.accept_string_literal(
            stop_chars=self.string_literal_stop,
            error_on_eof=False  # Just stop on EOF, no errors.
        )

    # Accept a CONSUME_REST literal.
    def accept_string_literal_consume_rest(self) -> t.Optional[Token]:
        return self.accept_string_literal(
            stop_chars=self.consume_rest_stop,
            error_on_eof=False  # Stop on EOF. No errors.
        )

    @staticmethod
    def accept_any_of(*f: t.Callable[[], t.Optional[Token]]) -> t.Optional[Token]:
        for fun in f:
            tok = fun()
            if tok is not None:
                return tok

        return None

    def handle_consume_rest_off(self, tok: Token) -> None:
        if tok.type in (TokenType.COMMAND_SEP, TokenType.CLOSE_BLOCK, TokenType.CLOSE_PAREN):
            self.previous_token_was_sep = True
            return

        # Test to see if we should enter CONSUME_REST state.
        # Only trigger CONSUME_REST if the previous token was a command separator.
        should_enter_consume_rest = (
                self.previous_token_was_sep and
                tok.type == TokenType.STRING_LITERAL and
                tok.value in self.consume_rest_triggers
        )
        self.previous_token_was_sep = False
        if should_enter_consume_rest:
            count = self.consume_rest_triggers[tok.value]

            if count == 0:
                self.consume_rest_state = TokenizeConsumeRestState.CONSUME
            else:
                self.consume_rest_state = TokenizeConsumeRestState.COUNTING
                self.consume_rest_count = count

    def handle_consume_rest_counting(self, tok: Token) -> None:
        self.previous_token_was_sep = False

        # Only count down on string literals.
        if tok.type == TokenType.STRING_LITERAL:
            self.consume_rest_count -= 1

            # Once countdown is over, CONSUME_REST on next token.
            if self.consume_rest_count == 0:
                self.consume_rest_state = TokenizeConsumeRestState.CONSUME

        # If we get any other token type, then cancel CONSUME_REST
        else:
            self.consume_rest_state = TokenizeConsumeRestState.OFF
            self.consume_rest_count = 0

    def handle_consume_rest_consume(self, tok: Token) -> None:
        # This function runs AFTER a CONSUME_REST consumption. So, just set consume_rest back to OFF.
        self.consume_rest_state = TokenizeConsumeRestState.OFF
        self.consume_rest_count = 0

    # TODO
    # Consume rest state handler. All this code is pretty ugly, and does not account
    # for more advanced usage.
    def handle_consume_rest(self, tok: Token) -> None:
        f_map: t.Mapping[TokenizeConsumeRestState, t.Callable[[Token], None]] = {
            TokenizeConsumeRestState.OFF: self.handle_consume_rest_off,
            TokenizeConsumeRestState.COUNTING: self.handle_consume_rest_counting,
            TokenizeConsumeRestState.CONSUME: self.handle_consume_rest_consume
        }

        f_map[self.consume_rest_state](tok)

    def next_token(self) -> Token:
        if self.consume_rest_state == TokenizeConsumeRestState.CONSUME:
            while True:
                tok = self.accept_any_of(
                    self.accept_whitespace
                )

                if tok is None:
                    break

                if tok.type == TokenType.WHITESPACE:
                    continue

            tok = self.accept_string_literal_consume_rest()
            if tok is None:
                self.error(
                    errors.TokenizeError,
                    "Got bad string literal during consume_rest"
                )
            logger.debug(f"tokenize: Got token {tok.type.name}:{repr(tok.value)}")
            tok.consume_rest = True  # Signal we got this token using CONSUME_REST

            self.handle_consume_rest(tok)
            return tok
        else:
            while True:
                tok = self.accept_any_of(
                    self.accept_eof,
                    self.accept_whitespace,
                    self.accept_single_char,
                    self.accept_string_literal_normal
                )

                if tok is None:
                    self.error(
                        errors.TokenizeError,
                        "Unexpectedly rejected all tokenizing functions."
                    )

                # Loop until we get a non-whitespace token.
                if tok.type != TokenType.WHITESPACE:
                    logger.debug(f"tokenize: Got token {tok.type.name}:{repr(tok.value)}")
                    self.handle_consume_rest(tok)
                    return tok

    def get_all_tokens(self) -> t.Sequence[Token]:
        tokens: t.MutableSequence[Token] = []

        while True:
            tok = self.next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                return tokens


class ParseContext:
    def __init__(self, tokenizer: Tokenizer):
        self.tokenizer = tokenizer
        self.lines = self.tokenizer.string.splitlines()
        self.input_tokens = self.tokenizer.get_all_tokens()
        self.tokens: t.MutableSequence[Token] = list(self.input_tokens)
        self.token: Token = Token(TokenType.WHITESPACE, "", 0, 0)

        self.next_token()

    def current_token(self) -> Token:
        return self.token

    def get_line(self) -> str:
        return self.lines[self.token.line]

    def next_token(self) -> None:
        if not self.tokens:
            logger.debug("End of tokens.")
            parse_error(
                self,
                errors.ParseEofError,
                "Unexpected end of script."
            )
        else:
            prev_token = self.token
            self.token = self.tokens.pop(0)

            logger.debug(f"Advance token: {str(prev_token)}->{str(self.token)}")


def parse_error(
    ctx: ParseContext,
    error: t.Type[errors.ParseError],
    message: str,
    fatal: bool = False
) -> t.NoReturn:
    e = error(
        ctx.token.line,
        ctx.token.position,
        ctx.tokenizer.string,
        message
    )

    e.fatal = fatal

    if not fatal:
        logger.debug("error")
    else:
        logger.debug("fatal error")

    raise e


def parse_get(
    ctx: ParseContext,
    type: TokenType
) -> t.Optional[Token]:
    token = ctx.current_token()

    logger.debug(f"parse_get: want {type.name}")

    if token.type == type:
        ctx.next_token()
        logger.debug(f"parse_get: accepted {str(token)}")
        return token
    else:
        logger.debug(f"parse_get: rejected {str(token)}")
        return None


def parse_expect(
    ctx: ParseContext,
    type: TokenType,
    fatal_on_error: bool = False
) -> Token:
    tok = parse_get(ctx, type)

    if tok is None:
        parse_error(
            ctx,
            errors.ParseExpectError,
            f"expected {type.name} here, but got {ctx.token.type.name}({ctx.token.value})",
            fatal=fatal_on_error
        )

    else:
        return tok


def parse_strtok(
    ctx: ParseContext
) -> ASTNode:
    node = ASTNode(
        ASTNodeType.STRING,
        parse_expect(ctx, TokenType.STRING_LITERAL)
    )

    return node


def parse_greedy(
    parser: ParserT
) -> t.Callable[[ParseContext], t.Sequence[ASTNode]]:
    def _(ctx: ParseContext) -> t.Sequence[ASTNode]:
        nodes: t.MutableSequence[ASTNode] = []

        while True:
            try:
                nodes.append(parser(ctx))
                logger.debug("parse_greedy: append success")
            except errors.ParseError as e:
                if e.fatal:
                    raise

                logger.debug("parse_greedy: append fail, return")
                return nodes

    return _


def parse_choice(
    *parsers: ParserT
) -> ParserT:
    def _(ctx: ParseContext) -> ASTNode:
        last_exc: t.Optional[errors.ParseError] = None

        for parser in parsers:
            try:
                node = parser(ctx)
                return node
            except errors.ParseError as e:
                last_exc = e

                if e.fatal:
                    break

        if last_exc is None:
            parse_error(
                ctx,
                errors.ParseError,
                "internal: no parsers provided for parse_choice"
            )
        else:
            raise last_exc

    return _


def expect(
    t_type: TokenType,
    fatal_on_error: bool = False
) -> ParserT:
    def _(ctx: ParseContext) -> ASTNode:
        node = ASTNode(
            ASTNodeType.NONE,
            parse_expect(ctx, t_type, fatal_on_error)
        )

        return node

    return _


def parse_try(
    parser: ParserT
) -> t.Callable[[ParseContext], bool]:
    def _(ctx: ParseContext) -> bool:
        try:
            parser(ctx)
            return True
        except errors.ParseError:
            return False

    return _


def expect_eof(ctx: ParseContext) -> ASTNode:
    try:
        parse_expect(ctx, TokenType.EOF)
    except errors.ParseEofError:
        pass

    return ASTNode(
        ASTNodeType.EOF,
        ctx.token
    )


expect_command_separator = expect(TokenType.COMMAND_SEP)


def parse_expansion_var(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion_var")
    return parse_strtok(ctx).wrap(ASTNodeType.EXPANSION_VAR, as_child=True)


def parse_expansion_call_args(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion_call_args")

    args = parse_greedy(parse_eventual_string)(ctx)
    first_tok: t.Optional[Token] = None

    if args:
        first_tok = args[0].tok

    args_node = ASTNode(
        ASTNodeType.EXPANSION_ARGUMENTS,
        first_tok
    )
    args_node.children.extend(args)

    return args_node


def parse_expansion_call(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion_call")
    call_node = expect(TokenType.OPEN_PAREN)(ctx).wrap(
        ASTNodeType.EXPANSION_CALL
    )

    call_node.children.append(parse_eventual_string(ctx))  # Expansion name
    call_node.children.append(parse_expansion_call_args(ctx))

    expect(TokenType.CLOSE_PAREN, fatal_on_error=True)(ctx)

    return call_node


def parse_expansion(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion")

    expansion_node = expect(TokenType.EXPANSION_SIGIL)(ctx).wrap(
        ASTNodeType.EXPANSION
    )

    multi_tok = parse_get(ctx, TokenType.MULTI_SIGIL)
    if multi_tok is None:
        expansion_node.children.append(
            ASTNode(ASTNodeType.EXPANSION_SINGLE, None)
        )
    else:
        expansion_node.children.append(
            ASTNode(ASTNodeType.EXPANSION_MULTI, multi_tok)
        )

    expansion_node.children.append(
        parse_choice(parse_expansion_call, parse_expansion_var)(ctx)
    )

    return expansion_node


parse_eventual_string = parse_choice(
    parse_expansion,
    parse_strtok
)


def parse_command_args(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_command_args")
    args_node = ASTNode(ASTNodeType.COMMAND_ARGUMENTS, None)
    args_node.children.extend(parse_greedy(parse_eventual_string)(ctx))

    if args_node.children:
        args_node.tok = args_node.children[0].tok

    return args_node


def parse_command(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_command")

    command_node = parse_eventual_string(ctx).wrap(
        ASTNodeType.COMMAND_CALL,
        as_child=True
    )
    command_node.children.append(parse_command_args(ctx))

    return command_node


def parse_control_args(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_control_args")
    args_node = expect(TokenType.OPEN_PAREN)(ctx).wrap(
        ASTNodeType.CONTROL_ARGUMENTS
    )
    args_node.children.extend(parse_greedy(parse_eventual_string)(ctx))
    expect(
        TokenType.CLOSE_PAREN,
        fatal_on_error=True
    )(ctx)

    return args_node


def parse_control(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_control")

    control_node = expect(TokenType.CONTROL_SIGIL)(ctx).wrap(
        ASTNodeType.CONTROL_CALL
    )
    control_node.children.append(parse_strtok(ctx))
    control_node.children.append(parse_control_args(ctx))
    control_node.children.append(parse_statement(ctx))

    return control_node


def parse_block_body(ctx: ParseContext, top_level: bool = False) -> t.Sequence[ASTNode]:
    logger.debug("parse_block_body")

    nodes: t.MutableSequence[ASTNode] = []

    while True:
        if ctx.token.type == TokenType.CLOSE_BLOCK:
            if top_level:
                parse_error(
                    ctx,
                    errors.ParseError,
                    "Unexpected block close.",
                    fatal=True
                )
            else:
                return nodes

        if ctx.token.type == TokenType.EOF:
            if top_level:
                return nodes
            else:
                parse_error(
                    ctx,
                    errors.ParseEofError,
                    "Unexpected end of script while parsing block.",
                    fatal=True
                )

        # If we hit a command separator, just consume it and continue.
        if parse_try(expect_command_separator)(ctx):
            continue

        # Actually try to parse the next statement. If that fails, it means we found some non-statement
        # structure inside a block, which is not legal. Error out with something more descriptive.
        try:
            node = parse_statement(ctx)
        except errors.ParseError:
            parse_error(
                ctx,
                errors.ParseError,
                "Expected statement or block here.",
                fatal=True
            )
            raise  # Not necessary, but satisfies linters.

        nodes.append(node)


def parse_block(ctx: ParseContext) -> ASTNode:
    node = expect(TokenType.OPEN_BLOCK)(ctx).wrap(
        ASTNodeType.BLOCK
    )
    node.children.extend(parse_block_body(ctx))
    expect(
        TokenType.CLOSE_BLOCK,
        fatal_on_error=True
    )(ctx)

    return node


parse_statement = parse_choice(
    parse_block,
    parse_control,
    parse_command
)


def parse_root(tokenizer: Tokenizer) -> ASTNode:
    ctx = ParseContext(tokenizer)
    root_node = ASTNode(ASTNodeType.ROOT, None)
    root_node.children.extend(parse_block_body(ctx, top_level=True))

    return root_node


def parse_scroll(tokenizer: Tokenizer) -> AST:
    return AST(parse_root(tokenizer), tokenizer.string)
