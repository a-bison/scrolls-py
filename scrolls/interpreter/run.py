"""
Code relating to the execution of `scrolls.ast.syntax.AST` objects.
"""

import logging
import types
import typing as t

from .. import ast
from .. import errors as base_errors
from . import callhandler, interpreter_errors, state, struct

__all__ = (
    "Interpreter",
)


logger = logging.getLogger(__name__)
T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)


class Interpreter:
    """
    The interpreter implementation for Scrolls. Configure through the `*_handlers` properties. Or, for a more organized
    configuration, see `scrolls.containers.DecoratorInterpreterConfig`.

    Args:
        context_cls: The `scrolls.interpreter.state.InterpreterContext` class to use when automatically instantiating new context objects.
            Must be `scrolls.interpreter.state.InterpreterContext` or a subclass of it.

        statement_limit: The number of statements allowed while executing a script. This is counted in the
            `scrolls.interpreter.state.InterpreterContext` object for a given run. If the number of executed statements exceeds this, an
            `scrolls.interpreter.interpreter_errors.InterpreterError` will be raised. If set to zero, then there is no statement limit.

        call_depth_limit: The number of levels deep the call stack is allowed to go. This is used to prevent
            denial of service through infinite recursion. If zero, then call depth is unlimited.
    """
    def __init__(
        self,
        context_cls: t.Type[state.InterpreterContext] = state.InterpreterContext,
        statement_limit: int = 0,
        call_depth_limit: int = 200
    ):
        self._command_handlers: callhandler.BaseCallHandlerContainer[None] = callhandler.BaseCallHandlerContainer()
        self._control_handlers: callhandler.BaseCallHandlerContainer[None] = callhandler.BaseCallHandlerContainer()
        self._expansion_handlers: callhandler.BaseCallHandlerContainer[str] = callhandler.BaseCallHandlerContainer()
        self._initializers: callhandler.BaseCallHandlerContainer[None] = callhandler.BaseCallHandlerContainer()

        self.context_cls = context_cls
        """
        The `scrolls.interpreter.state.InterpreterContext` class to use when automatically instantiating new context objects.
        Must be `scrolls.interpreter.state.InterpreterContext` or a subclass of it.
        """

        self.statement_limit = statement_limit
        self.call_depth_limit = call_depth_limit

    def over_statement_limit(self, context: state.InterpreterContext) -> bool:
        """
        Utility function. Checks whether the passed context has exceeded the statement limit set for this interpreter.
        """
        if self.statement_limit == 0:
            return False
        else:
            return context.statement_count > self.statement_limit

    def over_call_depth_limit(self, context: state.InterpreterContext) -> bool:
        """
        Utility function. Checks whether the passed context has exceeded the call stack depth limit set for this
        interpreter.
        """
        if self.call_depth_limit == 0:
            return False
        else:
            return len(context.call_stack) > self.call_depth_limit

    @property
    def command_handlers(self) -> callhandler.BaseCallHandlerContainer[None]:
        """The container of command handlers for this interpreter."""
        return self._command_handlers

    @property
    def control_handlers(self) -> callhandler.BaseCallHandlerContainer[None]:
        """The container of control handlers for this interpreter."""
        return self._control_handlers

    @property
    def expansion_handlers(self) -> callhandler.BaseCallHandlerContainer[str]:
        """The container of expansion handlers for this interpreter."""
        return self._expansion_handlers

    @property
    def initializers(self) -> callhandler.BaseCallHandlerContainer[None]:
        """The container of `scrolls.interpreter.callhandler.Initializer` instances for this interpreter."""
        return self._initializers

    def apply_initializers(self, context: state.InterpreterContext) -> None:
        """Apply this interpreter's context initializers to the given context object."""
        for init in self.initializers:
            init.handle_call(context)

    def run(
        self,
        script: str,
        context: t.Optional[state.InterpreterContext] = None,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ) -> state.InterpreterContext:
        """Run a Scrolls script.

        Args:
            script: The script to run.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.
            consume_rest_triggers: A mapping of triggers for the CONSUME_REST parsing feature.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `scrolls.interpreter.state.InterpreterContext` instance.
        """
        tokenizer = ast.Tokenizer(script, consume_rest_triggers)
        tree = ast.parse_scroll(tokenizer)
        return self.interpret_ast(tree, context)

    def init_context(self, context: state.InterpreterContext) -> None:
        """
        Initialize a context for this interpreter.
        """
        context.interpreter = self
        context.set_base_call()
        context.init_handlers(
            self.command_handlers,
            self.expansion_handlers
        )
        self.apply_initializers(context)

    def run_statement(
        self,
        statement: t.Union[str, ast.Tokenizer],
        context: t.Optional[state.InterpreterContext] = None,
    ) -> state.InterpreterContext:
        """Run a single Scrolls statement.

        Args:
            statement: The statement to run. Must be either a string, or a tokenizer populated with a valid Scrolls
                statement.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `scrolls.interpreter.state.InterpreterContext` instance.
        """
        # Set up parsing and parse statement
        if isinstance(statement, str):
            tokenizer = ast.Tokenizer(statement)
        else:
            tokenizer = statement

        statement_node = ast.parse_statement(tokenizer)

        # Interpret statement
        if context is None:
            context = self.context_cls(statement_node)

        self.init_context(context)
        self.interpret_statement(context, statement_node)

        return context

    def repl(
        self,
        on_error: t.Optional[t.Callable[[base_errors.ScrollError], None]] = None,
        prelude: t.Optional[str] = None
    ) -> None:
        """
        Drop into a REPL (read eval print loop).

        Args:
            on_error: A function to call when an error occurs. If `None`,
                      errors will stop the REPL.
            prelude: A scrolls script that will run before the repl starts.
        """
        stream = ast.REPLStream()
        tokenizer = ast.Tokenizer(stream)

        if prelude is not None:
            logger.debug("repl: Running prelude.")
            context = self.run(prelude)
            logger.debug("repl: Prelude complete.")
        else:
            logger.debug("repl: Running without prelude.")
            context = self.context_cls()
            self.init_context(context)

        while True:
            try:
                statement_node = ast.parse_statement(tokenizer)
                stream.set_statement()

                self.interpret_statement(context, statement_node)
            except interpreter_errors.InterpreterStop:
                return
            except interpreter_errors.InterpreterReturn:
                e = interpreter_errors.InterpreterError(
                    context,
                    f"returning only allowed in functions"
                )
                if on_error is not None:
                    on_error(e)
                    stream.set_statement()
                    stream.next_line()
                else:
                    raise e
            except KeyboardInterrupt:
                print("Keyboard interrupt.")
                return
            except base_errors.ScrollError as e:
                if on_error is not None:
                    on_error(e)
                    stream.set_statement()
                    stream.next_line()
                else:
                    raise

    @staticmethod
    def test_parse(
        script: str,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ) -> str:
        """
        Returns a JSON-formatted string showing the full `scrolls.ast.syntax.ASTNode` structure of a parsed script, including
        `consume_rest_triggers`.

        .. WARNING::
            For debugging and demonstration purposes only.
        """
        tokenizer = ast.Tokenizer(script, consume_rest_triggers)
        tree = ast.parse_scroll(tokenizer)
        return tree.prettify()

    def interpret_ast(
        self,
        tree: ast.AST,
        context: t.Optional[state.InterpreterContext] = None
    ) -> state.InterpreterContext:
        """
        Interprets a full AST structure.

        Args:
            tree: The AST to interpret.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `scrolls.interpreter.state.InterpreterContext` instance.
        """
        if context is None:
            context = self.context_cls(tree.root)

        self.init_context(context)

        try:
            self.interpret_root(context, tree.root)
        except interpreter_errors.InterpreterStop:
            logger.debug("Interpreter stop raised.")
            pass
        except interpreter_errors.InterpreterReturn:
            raise interpreter_errors.InterpreterError(
                context,
                f"returning only allowed in functions"
            )

        return context

    def interpret_root(self, context: state.InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.ROOT`."""
        self.interpret_block(context, node)

    def interpret_call(
        self,
        call_handler_container: callhandler.CallHandlerContainer[T_co],
        context: state.InterpreterContext,
        node: ast.ASTNode,
        expected_node_type: ast.ASTNodeType,
        pass_control_node: bool = False
    ) -> T_co:
        """
        Generic function for interpreting call nodes.

        Args:
            call_handler_container: The call handler container to check for call handlers.
            context: The interpreter context.
            node: The AST node to interpret.
            expected_node_type: The type of AST node to be expected.
            pass_control_node: Whether to pass `node.children[2]` into the control parameter of a call. Currently,
                this only applies to control calls. See `scrolls.interpreter.state.InterpreterContext.control_node`.

        Returns:
            The result of the call, if any.

        Related:
            `Interpreter.interpret_command` `Interpreter.interpret_control` `Interpreter.interpret_expansion_call`
        """

        if node.type != expected_node_type:
            raise interpreter_errors.InternalInterpreterError(
                context,
                f"interpret_call: name: Expected {expected_node_type.name}, got {node.type.name}"
            )

        name_node = node.children[0]
        args_node = node.children[1]
        arg_node_map: struct.ArgSourceMap[ast.ASTNode] = struct.ArgSourceMap()

        raw_call = list(self.interpret_string_or_expansion(context, name_node))

        if not raw_call:
            raise interpreter_errors.InterpreterError(
                context,
                f"Call name must not expand to empty string."
            )

        arg_node_map.add_args(raw_call[1:], name_node)

        for arg_node in args_node.children:
            new_args = self.interpret_string_or_expansion(context, arg_node)
            arg_node_map.add_args(new_args, arg_node)

            raw_call += new_args

        logger.debug(f"interpret_call: raw {raw_call}")
        call_name = raw_call[0]
        call_args: t.Sequence[str] = raw_call[1:]

        context.current_node = node
        control_node: t.Optional[ast.ASTNode]

        if pass_control_node:
            control_node = node.children[2]
        else:
            control_node = None

        context.push_call()
        if self.over_call_depth_limit(context):
            raise interpreter_errors.InterpreterError(
                context,
                f"Maximum call stack depth ({self.call_depth_limit}) exceeded."
            )

        context.set_call(call_name, call_args, arg_node_map, control_node=control_node)

        try:
            handler = call_handler_container.get_for_call(call_name)
        except KeyError:
            context.current_node = name_node
            raise interpreter_errors.MissingCallError(context, expected_node_type.name, call_name)

        try:
            result: T_co = handler.handle_call(context)
        except interpreter_errors.InterpreterReturn:
            # Ensure call stack is properly changed even on returns
            context.pop_call()

            raise

        context.pop_call()

        return result

    def interpret_control(self, context: state.InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.CONTROL_CALL`."""
        self.interpret_call(
            self.control_handlers,
            context,
            node,
            ast.ASTNodeType.CONTROL_CALL,
            pass_control_node=True
        )

    def interpret_command(self, context: state.InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.COMMAND_CALL`."""
        self.interpret_call(
            context.all_commands,
            context,
            node,
            ast.ASTNodeType.COMMAND_CALL
        )

    def interpret_variable_reference(self, context: state.InterpreterContext, node: ast.ASTNode) -> str:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.EXPANSION_VAR`."""
        context.current_node = node

        var_name = " ".join(self.interpret_string_or_expansion(context, node.children[0]))
        try:
            return context.get_var(var_name)
        except KeyError:
            raise interpreter_errors.InterpreterError(
                context, f"No such variable {var_name}."
            )

    def interpret_expansion_call(self, context: state.InterpreterContext, node: ast.ASTNode) -> str:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.EXPANSION_CALL`."""
        result = self.interpret_call(
            context.all_expansions,
            context,
            node,
            ast.ASTNodeType.EXPANSION_CALL
        )
        assert result is not None
        return result

    def interpret_sub_expansion(self, context: state.InterpreterContext, node: ast.ASTNode) -> str:
        """Utility. Interprets an expansion child node, which may be either
        `scrolls.ast.ast_constants.ASTNodeType.EXPANSION_VAR` or
        `scrolls.ast.ast_constants.ASTNodeType.EXPANSION_CALL`.
        """
        context.current_node = node

        if node.type == ast.ASTNodeType.EXPANSION_VAR:
            return self.interpret_variable_reference(context, node)
        elif node.type == ast.ASTNodeType.EXPANSION_CALL:
            return self.interpret_expansion_call(context, node)
        else:
            raise interpreter_errors.InternalInterpreterError(
                context,
                f"Bad expansion node type {node.type.name}"
            )

    def interpret_expansion(self, context: state.InterpreterContext, node: ast.ASTNode) -> t.Sequence[str]:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.EXPANSION`."""
        context.current_node = node

        multi_node, expansion_node = node.children

        if multi_node.type == ast.ASTNodeType.EXPANSION_SPREAD:
            multi = True
        elif multi_node.type == ast.ASTNodeType.EXPANSION_SINGLE:
            multi = False
        else:
            raise interpreter_errors.InternalInterpreterError(
                context,
                f"Bad expansion multi_node type {multi_node.type.name}"
            )

        string = self.interpret_sub_expansion(context, expansion_node)
        if multi:
            return [s.strip() for s in string.split()]
        else:
            return [string]

    def interpret_string_or_expansion(self, context: state.InterpreterContext, node: ast.ASTNode) -> t.Sequence[str]:
        """Utility. Interprets call names and arguments, which may be either
        `scrolls.ast.ast_constants.ASTNodeType.STRING` or
        `scrolls.ast.ast_constants.ASTNodeType.EXPANSION`
        """

        context.current_node = node

        if node.type == ast.ASTNodeType.STRING:
            return [node.str_content()]
        elif node.type == ast.ASTNodeType.EXPANSION:
            return self.interpret_expansion(context, node)
        else:
            raise interpreter_errors.InternalInterpreterError(
                context, f"Bad node type for string_or_expansion: {node.type.name}"
            )

    def interpret_block(self, context: state.InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.syntax.ASTNode` of type `scrolls.ast.ast_constants.ASTNodeType.BLOCK`."""
        context.current_node = node

        for sub_statement in context.current_node.children:
            self.interpret_statement(context, sub_statement)

    def interpret_statement(self, context: state.InterpreterContext, node: ast.ASTNode) -> None:
        """Utility. Interprets Scrolls statements, which may be `scrolls.ast.ast_constants.ASTNodeType.CONTROL_CALL`,
        `scrolls.ast.ast_constants.ASTNodeType.COMMAND_CALL`, or `scrolls.ast.ast_constants.ASTNodeType.BLOCK`.

        More often than not, this is the function that control calls will use to run the statement passed to
        `scrolls.interpreter.state.InterpreterContext.control_node`. See `scrolls.builtins.BuiltinControlHandler` for examples.
        """
        context.current_node = node

        node_type = context.current_node.type

        if node_type == ast.ASTNodeType.CONTROL_CALL:
            self.interpret_control(context, context.current_node)
        elif node_type == ast.ASTNodeType.COMMAND_CALL:
            self.interpret_command(context, context.current_node)
        elif node_type == ast.ASTNodeType.BLOCK:
            self.interpret_block(context, context.current_node)
        else:
            raise interpreter_errors.InternalInterpreterError(
                context, f"Bad statement type {node_type.name}"
            )

        context.statement_count += 1
        if self.over_statement_limit(context):
            raise interpreter_errors.InterpreterError(
                context,
                f"Exceeded maximum statement limit of {self.statement_limit}."
            )
