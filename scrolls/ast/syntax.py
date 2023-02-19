"""
Syntactic analysis.

See [ast: Syntactic Analysis](index.html#syntactic-analysis)
"""

import json
import logging
import typing as t

from .. import errors as base_errors
from . import ast_errors
from .ast_constants import ASTNodeType, TokenType
from .tokenizer import Token, Tokenizer

__all__ = (
    "AST",
    "ASTNode",
    "ASTStateError",
    "parse_scroll",
    "parse_statement"
)


logger = logging.getLogger(__name__)
ParserT = t.Callable[['ParseContext'], 'ASTNode']


class AST:
    """An Abstract Syntax Tree.

    Represents the syntactic structure of a script.
    """

    def __init__(self, root: 'ASTNode', script: str):
        self.root: ASTNode = root
        """The root `ASTNode` of this AST."""

        self.script: str = script
        """The script that generated this AST."""

    def prettify(self) -> str:
        """Returns a JSON-formatted string showing the full structure of this AST.

        .. WARNING::
            For debugging and demonstration purposes only.
        """
        return self.root.prettify()

    def __repr__(self) -> str:
        return f"ScrollAST({repr(self.root)}"


class ASTStateError(base_errors.ScrollError):
    """Generic tokenizer/parser error that includes an entire AST node.

    Raised by `ASTNode` functions on invalid state.

    Generally internal to the `scrolls` module. If one of these errors makes it out,
    something is probably wrong.
    """
    def __init__(self, node: 'ASTNode', message: str):
        self.node = node
        self.message = message

    def __str__(self) -> str:
        return self.message


class ASTNode:
    """
    A node within an `AST`.
    """
    __slots__ = (
        "children",
        "type",
        "_tok"
    )

    def __init__(self, type: ASTNodeType, token: t.Optional[Token]):
        self.children: t.MutableSequence['ASTNode'] = []
        """The child `ASTNode` objects of this node."""

        self.type = type
        """The `ASTNodeType` of this node."""

        self._tok: t.Optional[Token] = token

    def to_dict(self) -> t.Mapping[str, t.Any]:
        """
        Converts this object into a dict demonstrating its structure.

        Returns:
            A dictionary of the following form:

            ```json
            {
                "_type": "TYPENAME",
                "_tok": "TOKTYPE:'TOKVALUE'",
                "children": [...]
            }
            ```

            .. WARNING::
                This dictionary cannot be converted 1-1 back to a `ASTNode`. It is mainly meant for display
                purposes. See `ASTNode.prettify`.
        """

        mapping = {
            "_type": self.type.name,
            "_tok": str(self._tok),
            "children": [child.to_dict() for child in self.children]
        }

        return mapping

    def prettify(self) -> str:
        """
        Returns a JSON-formatted string showing the full structure of this `ASTNode`.

        .. WARNING::
            For debugging and demonstration purposes only.
        """

        s = json.dumps(self.to_dict(), sort_keys=True, indent=4)
        return s

    @property
    def tok(self) -> Token:
        """
        The token that generated this node. This should always be populated by `parse_scroll` under normal
        circumstances.

        Raises:
            ASTStateError: On get, if the token was never assigned.
        """

        if self._tok is None:
            raise ASTStateError(self, "cannot get token, is None")

        return self._tok

    @tok.setter
    def tok(self, token: Token) -> None:
        self._tok = token

    def has_token(self) -> bool:
        """
        Checks whether this node has a token assigned to it.
        """
        return self._tok is not None

    def wrap(self, node_type: ASTNodeType, as_child: bool = False) -> 'ASTNode':
        """
        Create a new node, and assign this node's token to the new node.

        .. WARNING::
            This is used internally by the parser during parsing and should generally not be called on finished ASTs.

        Args:
            node_type: The type of the new node.
            as_child: If `True`, add this node as a child of the new wrapper node.

        Returns:
            The newly created wrapper node.
        """
        new_node = ASTNode(
            node_type,
            self.tok
        )

        if as_child:
            new_node.children.append(self)

        return new_node

    def str_content(self) -> str:
        """
        Gets the string value of a `scrolls.ast.ast_constants.ASTNodeType.STRING` node.

        Raises:
            ASTStateError: If this node is not `scrolls.ast.ast_constants.ASTNodeType.STRING`.
        """
        if self.type != ASTNodeType.STRING:
            raise ASTStateError(self, "str_content requires STRING type node")

        assert self._tok is not None
        return self._tok.value

    def find_all(self, func: t.Callable[['ASTNode'], bool]) -> t.Sequence['ASTNode']:
        """
        Find all nodes in this tree for which `func` returns true.

        Args:
            func: A predicate which takes an `ASTNode` as input.

        Returns:
            A sequence of matching nodes.
        """

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


class ParseContext:
    def __init__(self, tokenizer: Tokenizer):
        self.tokenizer = tokenizer
        self.token: Token = Token(TokenType.WHITESPACE, "", 0, 0, tokenizer)

        self.next_token()

    def current_token(self) -> Token:
        return self.token

    def next_token(self) -> None:
        if self.tokenizer.stream.after_eof():
            logger.debug("End of tokens.")
            parse_error(
                self,
                ast_errors.ParseEofError,
                "Unexpected end of script."
            )
        else:
            prev_token = self.token
            self.token = self.tokenizer.next_token()

            logger.debug(f"Advance token: {str(prev_token)}->{str(self.token)}")


def parse_error(
    ctx: ParseContext,
    error: t.Type[ast_errors.ParseError],
    message: str,
    fatal: bool = False
) -> t.NoReturn:
    e = error(
        ctx.token.line,
        ctx.token.position,
        ctx.tokenizer.stream.history(),
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
            ast_errors.ParseExpectError,
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
            except ast_errors.ParseError as e:
                if e.fatal:
                    raise

                logger.debug("parse_greedy: append fail, return")
                return nodes

    return _


def parse_choice(
    *parsers: ParserT
) -> ParserT:
    def _(ctx: ParseContext) -> ASTNode:
        last_exc: t.Optional[ast_errors.ParseError] = None

        for parser in parsers:
            try:
                node = parser(ctx)
                return node
            except ast_errors.ParseError as e:
                last_exc = e

                if e.fatal:
                    break

        if last_exc is None:
            parse_error(
                ctx,
                ast_errors.ParseError,
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
        except ast_errors.ParseError:
            return False

    return _


def expect_eof(ctx: ParseContext) -> ASTNode:
    try:
        parse_expect(ctx, TokenType.EOF)
    except ast_errors.ParseEofError:
        pass

    return ASTNode(
        ASTNodeType.EOF,
        ctx.token
    )


expect_command_separator = expect(TokenType.COMMAND_SEP)


def parse_expansion_var(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion_var")
    var_name_node = parse_eventual_string(ctx).wrap(
        ASTNodeType.EXPANSION_VAR, as_child=True
    )

    return var_name_node


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
    call_node = expect(TokenType.OPEN_ARGS)(ctx).wrap(
        ASTNodeType.EXPANSION_CALL
    )

    call_node.children.append(parse_eventual_string(ctx))  # Expansion name
    call_node.children.append(parse_expansion_call_args(ctx))

    expect(TokenType.CLOSE_ARGS, fatal_on_error=True)(ctx)

    return call_node


def parse_expansion(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_expansion")

    expansion_node = expect(TokenType.EXPANSION_SIGIL)(ctx).wrap(
        ASTNodeType.EXPANSION
    )

    multi_tok = parse_get(ctx, TokenType.SPREAD_SIGIL)
    if multi_tok is None:
        expansion_node.children.append(
            ASTNode(ASTNodeType.EXPANSION_SINGLE, None)
        )
    else:
        expansion_node.children.append(
            ASTNode(ASTNodeType.EXPANSION_SPREAD, multi_tok)
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
    args_node = expect(TokenType.OPEN_ARGS)(ctx).wrap(
        ASTNodeType.CONTROL_ARGUMENTS
    )
    args_node.children.extend(parse_greedy(parse_eventual_string)(ctx))
    expect(
        TokenType.CLOSE_ARGS,
        fatal_on_error=True
    )(ctx)

    return args_node


def parse_control(ctx: ParseContext) -> ASTNode:
    logger.debug("parse_control")

    control_node = expect(TokenType.CONTROL_SIGIL)(ctx).wrap(
        ASTNodeType.CONTROL_CALL
    )
    control_node.children.append(parse_strtok(ctx))

    try:
        # Try to parse statement first, and count no () as no arguments
        statement_node = _parse_statement(ctx)
        args_node = ASTNode(ASTNodeType.CONTROL_ARGUMENTS, statement_node.tok)

        control_node.children.append(args_node)
        control_node.children.append(statement_node)
    except ast_errors.ParseError:
        control_node.children.append(parse_control_args(ctx))
        control_node.children.append(_parse_statement(ctx))

    return control_node


def parse_block_body(ctx: ParseContext, top_level: bool = False) -> t.Sequence[ASTNode]:
    logger.debug("parse_block_body")

    nodes: t.MutableSequence[ASTNode] = []

    while True:
        if ctx.token.type == TokenType.CLOSE_BLOCK:
            if top_level:
                parse_error(
                    ctx,
                    ast_errors.ParseError,
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
                    ast_errors.ParseEofError,
                    "Unexpected end of script while parsing block.",
                    fatal=True
                )

        # If we hit a command separator, just consume it and continue.
        if parse_try(expect_command_separator)(ctx):
            continue

        # Actually try to parse the next statement. If that fails, it means we found some non-statement
        # structure inside a block, which is not legal. Error out with something more descriptive.
        try:
            node = _parse_statement(ctx)
        except ast_errors.ParseError:
            parse_error(
                ctx,
                ast_errors.ParseError,
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


_parse_statement = parse_choice(
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
    """
    Parse a script (wrapped in a `scrolls.ast.tokenizer.Tokenizer`) and convert it to an `scrolls.ast.syntax.AST`.
    See [Using The Parser](index.html#using-the-parser).
    """
    return AST(parse_root(tokenizer), tokenizer.stream.history())


def parse_statement(tokenizer: Tokenizer) -> ASTNode:
    """
    Parse a single statement from a `scrolls.ast.tokenizer.Tokenizer`.
    """
    ctx = ParseContext(tokenizer)
    return _parse_statement(ctx)
