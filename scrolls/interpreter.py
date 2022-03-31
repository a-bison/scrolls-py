import abc
import dataclasses
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
    "CallHandlerContainer",
    "MutableCallHandlerContainer",
    "BaseCallHandlerContainer",
    "RuntimeCallHandler",
    "CallbackCallHandler",
    "InterpreterStop"
)

logger = logging.getLogger(__name__)

T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)
AnyContextTV = t.TypeVar("AnyContextTV", bound='InterpreterContext')


class ArgSourceMap(dict[int, T], t.Generic[T]):
    """Utility class that maps arguments to some source."""

    def __init__(self, *args: t.Any, **kwargs: t.Any):
        super().__init__(*args, **kwargs)

        self.count = 0

    def add_args(self, args: t.Sequence, source: T) -> None:
        for i, _ in enumerate(args):
            self[i + self.count] = source

        self.count += len(args)


@dataclasses.dataclass
class CallContext:
    call_name: str
    args: t.Sequence[str]
    arg_nodes: ArgSourceMap[ast.ASTNode]
    control_node: t.Optional[ast.ASTNode] = None
    return_value: t.Optional[t.Any] = None
    runtime_call: bool = False


class ScopedVarStore:
    def __init__(self) -> None:
        self.scopes: t.MutableSequence[t.MutableMapping[str, str]] = []
        self.new_scope()  # There should always be one scope.

    def new_scope(self) -> None:
        self.scopes.append({})

    def destroy_scope(self) -> None:
        if len(self.scopes) == 1:
            # there should always be at least one scope
            raise ValueError("There must be at least one scope.")

        self.scopes.pop()

    def get_scope_for(self, name: str) -> t.MutableMapping[str, str]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope

        raise KeyError('name')

    @property
    def current_scope(self) -> t.MutableMapping[str, str]:
        return self.scopes[-1]

    def get_var(self, name: str) -> str:
        return self.get_scope_for(name)[name]

    def set_var(self, name: str, value: str) -> None:
        self.current_scope[name] = value

    def del_var(self, name: str) -> None:
        del self.current_scope[name]


class InterpreterContext:
    """
    Base class for the command interpreter context.
    """
    def __init__(self, *_: t.Any):
        self._current_node: t.Optional[ast.ASTNode] = None
        self._call_context: t.Optional[CallContext] = None
        self._interpreter: t.Optional[Interpreter] = None
        self._vars = ScopedVarStore()
        self._script: t.Optional[str] = None
        self.statement_count = 0

        self._call_stack: t.MutableSequence[CallContext] = []
        self._command_handlers: BaseCallHandlerContainer[None] = BaseCallHandlerContainer()
        self._expansion_handlers: BaseCallHandlerContainer[str] = BaseCallHandlerContainer()

    @property
    def vars(self) -> ScopedVarStore:
        return self._vars

    def set_var(self, name: str, value: str) -> None:
        self.vars.set_var(name, value)

    def del_var(self, name: str) -> None:
        self.vars.del_var(name)

    def get_var(self, name: str) -> str:
        return self.vars.get_var(name)

    @property
    def runtime_commands(self) -> 'BaseCallHandlerContainer[None]':
        return self._command_handlers

    @property
    def runtime_expansions(self) -> 'BaseCallHandlerContainer[str]':
        return self._expansion_handlers

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
        if self._call_context is None:
            raise InternalInterpreterError(
                self, "Current context is not a call."
            )

    @property
    def call_stack(self) -> t.Sequence[CallContext]:
        return self._call_stack

    @property
    def call_context(self) -> CallContext:
        self._call_check()
        return t.cast(CallContext, self._call_context)

    @property
    def call_name(self) -> str:
        self._call_check()
        return self.call_context.call_name

    @property
    def args(self) -> t.Sequence[str]:
        self._call_check()
        return self.call_context.args

    @property
    def arg_nodes(self) -> ArgSourceMap[ast.ASTNode]:
        self._call_check()
        return self.call_context.arg_nodes

    @property
    def control_node(self) -> ast.ASTNode:
        if self.call_context.control_node is None:
            raise InternalInterpreterError(
                self, "Current context is not a control call."
            )

        return self.call_context.control_node

    def set_call(
        self,
        command: str,
        args: t.Sequence[str],
        arg_nodes: ArgSourceMap[ast.ASTNode],
        control_node: t.Optional[ast.ASTNode] = None
    ) -> None:
        self._call_context = CallContext(
            command,
            args,
            arg_nodes,
            control_node
        )

    def in_call(self) -> bool:
        return self._call_context is not None

    def reset_call(self) -> None:
        self._call_context = None

    def push_call(self) -> None:
        self._call_check()
        self._call_stack.append(self.call_context)

    def pop_call(self) -> None:
        if not self._call_stack:
            raise InternalInterpreterError(
                self,
                f"Cannot pop call. No calls pushed."
            )

        ctx = self._call_stack.pop()
        self._call_context = ctx

    # In order to set a return value, we need to traverse up the
    # context stack in order to find one actually created by a dynamically
    # generated call.
    def set_retval(self, retval: str) -> None:
        self._call_check()

        if not self.call_stack:
            raise InterpreterError(
                self,
                f"cannot return, no call stack (outside calls)"
            )

        for ctx in reversed(self.call_stack):
            if ctx.runtime_call:
                ctx.return_value = retval
                return

        raise InterpreterError(
            self,
            f"cannot return outside of function"
        )


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


class Initializer(abc.ABC):
    @abc.abstractmethod
    def handle_call(self, context: AnyContextTV) -> None: ...

    def __contains__(self, command_name: str) -> bool:
        return False


class RuntimeCallHandler(t.Generic[T_co]):
    """
    A basic call handler that maps names to AST nodes.
    """
    def __init__(self) -> None:
        self.calls: t.MutableMapping[str, tuple[ast.ASTNode, t.Sequence[str]]] = {}

    def define(self, name: str, node: ast.ASTNode, params: t.Sequence[str]) -> None:
        self.calls[name] = (node, params)

    def undefine(self, name: str) -> None:
        del self.calls[name]

    def handle_call(self, context: InterpreterContext) -> T_co:
        node, params = self.calls[context.call_name]

        if len(params) != len(context.args):
            raise InterpreterError(
                context,
                f"{context.call_name}: Invalid number of arguments (expected {len(params)})"
            )

        context.vars.new_scope()
        for param, arg in zip(params, context.args):
            context.set_var(param, arg)

        context.call_context.runtime_call = True
        try:
            context.interpreter.interpret_statement(context, node)
        except InterpreterReturn:
            pass

        context.vars.destroy_scope()

        # TODO Fix typing here
        return t.cast(T_co, context.call_context.return_value)

    def __contains__(self, command_name: str) -> bool:
        return command_name in self.calls


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
CallbackExpansionHandler = CallbackCallHandler[str]
CallbackInitializerHandler = CallbackCallHandler[None]


class CallHandlerContainer(t.Protocol[T_co]):
    """
    A read-only call handler container.
    """
    def get(self, name: str) -> CallHandler[T_co]: ...
    def get_for_call(self, name: str) -> CallHandler[T_co]: ...
    def __iter__(self) -> t.Iterator[CallHandler[T_co]]: ...


class MutableCallHandlerContainer(CallHandlerContainer[T], t.Protocol[T]):
    """
    A mutable call handler container.
    """
    def add(self, handler: CallHandler[T], name: str = "") -> None: ...
    def remove(self, handler: t.Union[CallHandler[T], str]) -> None: ...


class BaseCallHandlerContainer(t.Generic[T]):
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

    def get(self, name: str) -> CallHandler[T]:
        return self._handlers[name]

    def get_for_call(self, name: str) -> CallHandler[T]:
        """
        Get the handler for a given command name.
        """
        for handler in self._handlers.values():
            if name in handler:
                return handler

        raise KeyError(name)

    def __iter__(self) -> t.Iterator[CallHandler[T]]:
        yield from self._handlers.values()


class ChoiceCallHandlerContainer(t.Generic[T]):
    def __init__(self, *containers: CallHandlerContainer[T]):
        self.containers = containers

    def get(self, name: str) -> CallHandler[T]:
        for container in self.containers:
            try:
                return container.get(name)
            except KeyError:
                pass

        raise KeyError(name)

    def get_for_call(self, name: str) -> CallHandler[T]:
        for container in self.containers:
            try:
                return container.get_for_call(name)
            except KeyError:
                pass

        raise KeyError(name)

    def __iter__(self) -> t.Iterator[CallHandler[T]]:
        for container in self.containers:
            yield from container


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
        message = f"{call_type.capitalize()} '{call_name}' not found."
        super().__init__(
            ctx, message
        )


class InternalInterpreterError(InterpreterError):
    def __init__(self, context: InterpreterContext, message: str):
        super().__init__(
            context,
            "INTERNAL ERROR. If you see this, please report it!\n" + message
        )


class InterpreterStop(errors.ScrollError):
    """
    An exception raised to stop the interpreter.
    """
    def __init__(self) -> None:
        super().__init__("InterpreterStop")


class InterpreterReturn(errors.ScrollError):
    """
    An exception raised to signal a return from a runtime call.
    """
    def __init__(self) -> None:
        super().__init__("InterpreterReturn")


class Interpreter:
    """
    The interpreter implementation for Scrolls.
    """
    def __init__(
        self,
        context_cls: t.Type[InterpreterContext] = InterpreterContext,
        statement_limit: int = 0,
        call_depth_limit: int = 200
    ):
        self._command_handlers: BaseCallHandlerContainer[None] = BaseCallHandlerContainer()
        self._control_handlers: BaseCallHandlerContainer[None] = BaseCallHandlerContainer()
        self._expansion_handlers: BaseCallHandlerContainer[str] = BaseCallHandlerContainer()
        self._initializers: BaseCallHandlerContainer[None] = BaseCallHandlerContainer()
        self.context_cls = context_cls

        self.statement_limit = statement_limit
        self.call_depth_limit = call_depth_limit

    def over_statement_limit(self, context: InterpreterContext) -> bool:
        if self.statement_limit == 0:
            return False
        else:
            return context.statement_count > self.statement_limit

    def over_call_depth_limit(self, context: InterpreterContext) -> bool:
        if self.call_depth_limit == 0:
            return False
        else:
            return len(context.call_stack) > self.call_depth_limit

    @property
    def command_handlers(self) -> BaseCallHandlerContainer[None]:
        return self._command_handlers

    @property
    def control_handlers(self) -> BaseCallHandlerContainer[None]:
        return self._control_handlers

    @property
    def expansion_handlers(self) -> BaseCallHandlerContainer[str]:
        return self._expansion_handlers

    @property
    def initializers(self) -> BaseCallHandlerContainer[None]:
        return self._initializers

    def apply_initializers(self, context: InterpreterContext) -> None:
        for init in self.initializers:
            init.handle_call(context)

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
        self.apply_initializers(context)

        try:
            self.interpret_root(context, tree.root)
        except InterpreterStop:
            logger.debug("Interpreter stop raised.")
            pass
        except InterpreterReturn:
            raise InterpreterError(
                context,
                f"returning only allowed in functions"
            )

        return context

    def interpret_root(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        self.interpret_block(context, node)

    def interpret_call(
        self,
        call_handler_container: CallHandlerContainer[T_co],
        context: InterpreterContext,
        node: ast.ASTNode,
        expected_node_type: ast.ASTNodeType,
        pass_control_node: bool = False
    ) -> T_co:
        """
        Generic function for interpreting call nodes.
        """

        if node.type != expected_node_type:
            raise InternalInterpreterError(
                context,
                f"interpret_call: name: Expected {expected_node_type.name}, got {node.type.name}"
            )

        name_node = node.children[0]
        args_node = node.children[1]
        arg_node_map: ArgSourceMap[ast.ASTNode] = ArgSourceMap()

        raw_call = list(self.interpret_string_or_expansion(context, name_node))

        if not raw_call:
            raise InterpreterError(
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

        if context.in_call():
            context.push_call()
            if self.over_call_depth_limit(context):
                raise InterpreterError(
                    context,
                    f"Maximum call stack depth ({self.call_depth_limit}) exceeded."
                )

        context.set_call(call_name, call_args, arg_node_map, control_node=control_node)

        try:
            handler = call_handler_container.get_for_call(call_name)
        except KeyError:
            context.current_node = name_node
            raise MissingCallError(context, expected_node_type.name, call_name)

        try:
            result: T_co = handler.handle_call(context)
        except InterpreterReturn:
            # Ensure call stack is properly changed even on returns
            if context.call_stack:
                context.pop_call()
            else:
                context.reset_call()

            raise

        if context.call_stack:
            context.pop_call()
        else:
            context.reset_call()

        return result

    def interpret_control(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        self.interpret_call(
            self.control_handlers,
            context,
            node,
            ast.ASTNodeType.CONTROL_CALL,
            pass_control_node=True
        )

    def interpret_command(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        self.interpret_call(
            ChoiceCallHandlerContainer(
                context.runtime_commands,
                self.command_handlers
            ),
            context,
            node,
            ast.ASTNodeType.COMMAND_CALL
        )

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

    def interpret_expansion_call(self, context: InterpreterContext, node: ast.ASTNode) -> str:
        result = self.interpret_call(
            ChoiceCallHandlerContainer(
                context.runtime_expansions,
                self.expansion_handlers
            ),
            context,
            node,
            ast.ASTNodeType.EXPANSION_CALL
        )
        assert result is not None
        return result

    def interpret_sub_expansion(self, context: InterpreterContext, node: ast.ASTNode) -> str:
        """Get the raw string for an expansion."""
        context.current_node = node

        if node.type == ast.ASTNodeType.EXPANSION_VAR:
            return self.interpret_variable_reference(context, node.children[0])
        elif node.type == ast.ASTNodeType.EXPANSION_CALL:
            return self.interpret_expansion_call(context, node)
        else:
            raise InternalInterpreterError(
                context,
                f"Bad expansion node type {node.type.name}"
            )

    def interpret_expansion(self, context: InterpreterContext, node: ast.ASTNode) -> t.Sequence[str]:
        context.current_node = node

        multi_node, expansion_node = node.children

        if multi_node.type == ast.ASTNodeType.EXPANSION_MULTI:
            multi = True
        elif multi_node.type == ast.ASTNodeType.EXPANSION_SINGLE:
            multi = False
        else:
            raise InternalInterpreterError(
                context,
                f"Bad expansion multi_node type {multi_node.type.name}"
            )

        str = self.interpret_sub_expansion(context, expansion_node)
        if multi:
            return [s.strip() for s in str.split()]
        else:
            return [str]

    def interpret_string_or_expansion(self, context: InterpreterContext, node: ast.ASTNode) -> t.Sequence[str]:
        context.current_node = node

        if node.type == ast.ASTNodeType.STRING:
            return [node.str_content()]
        elif node.type == ast.ASTNodeType.EXPANSION:
            return self.interpret_expansion(context, node)
        else:
            raise InternalInterpreterError(
                context, f"Bad node type for string_or_expansion: {node.type.name}"
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

        context.statement_count += 1
        if self.over_statement_limit(context):
            raise InterpreterError(
                context,
                f"Exceeded maximum statement limit of {self.statement_limit}."
            )
