import logging
import types
import typing as t

from . import ast, errors

__all__ = (
    "InterpreterContext",
    "CallHandler",
    "CallbackCommandHandler",
    "CallbackControlHandler",
    "Interpreter",
    "InterpreterError",
    "InternalInterpreterError",
    "ScrollCallback",
    "DebugCommandHandler",
    "StandardControlHandler",
    "CallHandlerContainer",
    "CallbackCallHandler"
)

logger = logging.getLogger(__name__)

T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)
AnyContextTV = t.TypeVar("AnyContextTV", bound='InterpreterContext')


class InterpreterContext:
    """
    Base class for the command interpreter context.
    """
    def __init__(self, *_: t.Any):
        self._current_node: t.Optional[ast.ASTNode] = None
        self._call_name: t.Optional[str] = None
        self._args: t.Sequence[str] = []
        self._arg_nodes: t.Sequence[ast.ASTNode] = []
        self._interpreter: t.Optional[Interpreter] = None
        self._control_node: t.Optional[ast.ASTNode] = None
        self._vars: t.MutableMapping[str, str] = {}
        self._script: t.Optional[str] = None

    def set_var(self, name: str, value: str) -> None:
        self._vars[name] = value

    def del_var(self, name: str) -> None:
        del self._vars[name]

    def get_var(self, name: str) -> str:
        return self._vars[name]

    @property
    def script(self) -> str:
        if self._script is None:
            raise InternalInterpreterError(
                self, "Script is not initialized."
            )

        return self._script

    @script.setter
    def script(self, s: str) -> None:
        self._script = s

    @property
    def interpreter(self) -> 'Interpreter':
        if self._interpreter is None:
            raise InternalInterpreterError(
                self, "Interpreter is not initialized."
            )

        return self._interpreter

    @interpreter.setter
    def interpreter(self, interpreter: 'Interpreter') -> None:
        self._interpreter = interpreter

    @property
    def current_node(self) -> ast.ASTNode:
        if self._current_node is None:
            raise InternalInterpreterError(
                self, "Current node is not initialized."
            )

        return self._current_node

    @current_node.setter
    def current_node(self, node: ast.ASTNode) -> None:
        self._current_node = node

    def _call_check(self) -> None:
        if self._call_name is None:
            raise InternalInterpreterError(
                self, "Current context is not a call."
            )

    @property
    def call_name(self) -> str:
        self._call_check()
        return t.cast(str, self._call_name)

    @property
    def args(self) -> t.Sequence[str]:
        self._call_check()
        return self._args

    @property
    def arg_nodes(self) -> t.Sequence[ast.ASTNode]:
        self._call_check()
        return self._arg_nodes

    @property
    def control_node(self) -> ast.ASTNode:
        if self._control_node is None:
            raise InternalInterpreterError(
                self, "Current context is not a control call."
            )

        return self._control_node

    def set_call(
        self,
        command: str,
        args: t.Sequence[str],
        arg_nodes: t.Sequence[ast.ASTNode],
        control_node: t.Optional[ast.ASTNode] = None
    ) -> None:
        self._call_name = command
        self._args = args
        self._arg_nodes = arg_nodes
        self._control_node = control_node

    def reset_call(self) -> None:
        self._call_name = None
        self._args = []
        self._arg_nodes = []
        self._control_node = None


class CallHandler(t.Protocol[T_co]):
    """
    The minimum interface required to implement a call handler.
    """
    def handle_call(self, context: AnyContextTV) -> T_co: ...
    def __contains__(self, command_name: str) -> bool: ...


class ScrollCallback(t.Protocol[T_co]):
    """
    Protocol for Callbacks passed into CallbackCallHandlers.
    """
    def __call__(self, context: AnyContextTV) -> T_co: ...


class CallbackCallHandler(t.Generic[T_co]):
    """
    A basic call handler that uses Callables (ScrollCallback[T]) to
    implement a call handler.
    """
    def __init__(self) -> None:
        self.calls: t.MutableMapping[str, ScrollCallback[T_co]] = {}
        self.aliases: t.MutableMapping[str, str] = {}

    def add_call(self, name: str, command: ScrollCallback[T_co]) -> None:
        self.calls[name] = command

    def add_alias(self, alias: str, name: str) -> None:
        self.aliases[alias] = name

    def remove_call(self, name: str) -> None:
        del self.calls[name]

        # Delete all aliases associated with the name.
        for key, value in self.aliases.items():
            if value == name:
                del self.aliases[key]

    def get_callback(self, name: str) -> ScrollCallback[T_co]:
        if name in self.calls:
            return self.calls[name]

        return self.calls[self.aliases[name]]

    def handle_call(self, context: InterpreterContext) -> T_co:
        return self.get_callback(context.call_name)(context)

    def __contains__(self, command_name: str) -> bool:
        return (
            command_name in self.calls or
            command_name in self.aliases
        )


CallbackCommandHandler = CallbackCallHandler[None]
CallbackControlHandler = CallbackCallHandler[None]


class DebugCommandHandler(CallbackCommandHandler):
    """
    Implements debugging commands.
    """
    def __init__(self) -> None:
        super().__init__()

        self.add_call("print", self.printcommand)

    def printcommand(self, context: InterpreterContext) -> None:
        print(" ".join(context.args))


class StandardControlHandler(CallbackControlHandler):
    """
    Implements built-in control statements
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("repeat", self.repeat)
        self.add_call("for", self._for)

    def repeat(self, context: InterpreterContext) -> None:
        interpreter = context.interpreter

        if len(context.args) != 1:
            raise InterpreterError(
                context,
                "repeat requires exactly one argument, the number of times to repeat"
            )

        context.current_node = context.arg_nodes[0]

        try:
            repeat_times = int(context.args[0])
        except ValueError:
            raise InterpreterError(
                context,
                f"'{context.args[0]}' is not a valid integer"
            )

        if repeat_times > interpreter.repeat_limit:
            raise InterpreterError(
                context,
                f"cannot repeat more than {interpreter.repeat_limit} times"
            )

        control_node = context.control_node
        for _ in range(repeat_times):
            interpreter.interpret_statement(context, control_node)

    def _for(self, context: InterpreterContext) -> None:
        interpreter = context.interpreter

        if not context.args or len(context.args) < 3:
            raise InterpreterError(
                context,
                "bad format in !for: expected !for(VARNAME in ARGS)"
            )

        var_name, _in, *items = context.args

        if _in != "in":
            context.current_node = context.arg_nodes[1]
            raise InterpreterError(
                context,
                f"unexpected token '{_in}', should be 'in'"
            )

        control_node = context.control_node
        for item in items:
            context.set_var(var_name, item)
            interpreter.interpret_statement(context, control_node)

        context.del_var(var_name)


class CallHandlerContainer(t.Generic[T]):
    """
    Generic container for ScrollCallHandlers.
    """
    def __init__(self) -> None:
        self._handlers: t.MutableMapping[str, CallHandler[T]] = {}

    def add(self, handler: CallHandler[T], name: str = "") -> None:
        if not name:
            name = handler.__class__.__qualname__

        logger.debug(f"Register call handler {name}")
        self._handlers[name] = handler

    def remove(self, handler: t.Union[CallHandler[T], str]) -> None:
        if isinstance(handler, str):
            name = handler
        else:
            name = handler.__class__.__qualname__

        del self._handlers[name]

    def get_for_call(self, name: str) -> CallHandler[T]:
        """
        Get the handler for a given command name.
        """
        for handler in self._handlers.values():
            if name in handler:
                return handler

        raise KeyError(name)


class InterpreterError(errors.PositionalError):
    def __init__(self, ctx: InterpreterContext, message: str):
        self.ctx = ctx

        if self.ctx.current_node.has_token():
            tok = self.ctx.current_node.tok
            super().__init__(
                tok.line,
                tok.position,
                self.ctx.script,
                message
            )
        else:
            super().__init__(
                0,
                0,
                "",
                message
            )

    def __str__(self) -> str:
        if self.ctx.current_node.has_token():
            return super().__str__()
        else:
            return "Interpreter error on node with uninitialized token."


class MissingCallError(InterpreterError):
    """
    Generic interpreter error for missing calls.
    """
    def __init__(self, ctx: InterpreterContext, call_type: str, call_name: str):
        self.call = call_name
        message = f"{call_type.capitalize()} call {call_name} not found."
        super().__init__(
            ctx, message
        )


class MissingCommandError(MissingCallError):
    def __init__(self, ctx: InterpreterContext, command_name: str):
        super().__init__(
            ctx,
            "command",
            command_name
        )


class MissingControlError(MissingCallError):
    def __init__(self, ctx: InterpreterContext, control_name: str):
        super().__init__(
            ctx,
            "control",
            control_name
        )


class InternalInterpreterError(InterpreterError):
    def __init__(self, context: InterpreterContext, message: str):
        super().__init__(
            context,
            "INTERNAL ERROR. If you see this, please report it!\n" + message
        )


class Interpreter:
    """
    The interpreter implementation for Scrolls.
    """
    def __init__(
        self,
        context_cls: t.Type[InterpreterContext] = InterpreterContext
    ):
        self._command_handlers: CallHandlerContainer[None] = CallHandlerContainer()
        self._control_handlers: CallHandlerContainer[None] = CallHandlerContainer()
        self.context_cls = context_cls

        self.repeat_limit = 20
        self._control_handlers.add(StandardControlHandler())

    @property
    def command_handlers(self) -> CallHandlerContainer[None]:
        return self._command_handlers

    @property
    def control_handlers(self) -> CallHandlerContainer[None]:
        return self._control_handlers

    def run(
        self,
        script: str,
        context: t.Optional[InterpreterContext] = None,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ) -> InterpreterContext:
        tokenizer = ast.Tokenizer(script, consume_rest_triggers)
        tree = ast.parse_scroll(tokenizer)
        return self.interpret_ast(tree, context)

    def run_statement(
        self,
        statement: str,
        context: t.Optional[InterpreterContext] = None,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({}),
        consume_rest_consumes_all: bool = False
    ) -> InterpreterContext:
        # Set up parsing and parse statement
        tokenizer = ast.Tokenizer(statement, consume_rest_triggers)
        tokenizer.set_consume_rest_all(consume_rest_consumes_all)
        parse_ctx = ast.ParseContext(tokenizer)
        statement_node = ast.parse_statement(parse_ctx)

        # Interpret statement
        if context is None:
            context = self.context_cls(statement_node)
            context.interpreter = self
            context.script = statement

        self.interpret_statement(context, statement_node)

        return context

    @staticmethod
    def test_parse(
        script: str,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ) -> str:
        tokenizer = ast.Tokenizer(script, consume_rest_triggers)
        tree = ast.parse_scroll(tokenizer)
        return tree.prettify()

    def interpret_ast(
        self,
        tree: ast.AST,
        context: t.Optional[InterpreterContext] = None
    ) -> InterpreterContext:
        if context is None:
            context = self.context_cls(tree.root)

        context.interpreter = self
        context.script = tree.script
        self.interpret_root(context, tree.root)

        return context

    def interpret_root(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        self.interpret_block(context, node)

    def interpret_control(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        context.current_node = node

        name_node, args_node, control_node = tuple(node.children)
        control_name = name_node.str_content()
        control_args: t.Sequence = [arg_node.str_content() for arg_node in args_node.children]

        context.set_call(control_name, control_args, args_node.children, control_node=control_node)

        try:
            handler = self.control_handlers.get_for_call(control_name)
        except KeyError:
            context.current_node = name_node
            raise MissingControlError(context, control_name)

        handler.handle_call(context)
        context.reset_call()

    def interpret_command(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        name_node, args_node = tuple(node.children)
        command_name: str = self.interpret_maybe_string(context, name_node)
        command_args: t.Sequence = [self.interpret_maybe_string(context, arg_node) for arg_node in args_node.children]

        context.current_node = node

        context.set_call(command_name, command_args, args_node.children)

        try:
            handler = self.command_handlers.get_for_call(command_name)
        except KeyError:
            context.current_node = name_node
            raise MissingCommandError(context, command_name)

        handler.handle_call(context)
        context.reset_call()

    @staticmethod
    def interpret_variable_reference(context: InterpreterContext, node: ast.ASTNode) -> str:
        context.current_node = node

        var_name = node.str_content()
        try:
            return context.get_var(var_name)
        except KeyError:
            raise InterpreterError(
                context, f"No such variable {var_name}."
            )

    def interpret_maybe_string(self, context: InterpreterContext, node: ast.ASTNode) -> str:
        context.current_node = node

        if node.type == ast.ASTNodeType.STRING:
            return node.str_content()
        elif node.type == ast.ASTNodeType.EXPANSION_VAR:
            return self.interpret_variable_reference(context, node.children[0])
        else:
            raise InternalInterpreterError(
                context, f"Bad node type for maybe_string: {node.type.name}"
            )

    def interpret_block(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        context.current_node = node

        for sub_statement in context.current_node.children:
            self.interpret_statement(context, sub_statement)

    def interpret_statement(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        context.current_node = node

        type = context.current_node.type

        if type == ast.ASTNodeType.CONTROL_CALL:
            self.interpret_control(context, context.current_node)
        elif type == ast.ASTNodeType.COMMAND_CALL:
            self.interpret_command(context, context.current_node)
        elif type == ast.ASTNodeType.BLOCK:
            self.interpret_block(context, context.current_node)
        else:
            raise InternalInterpreterError(
                context, f"Bad statement type {type.name}"
            )
