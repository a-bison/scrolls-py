"""
Call handler protocols and implementations.
"""

import abc
import dataclasses
import logging
import typing as t
import uuid

from .. import ast
from . import interpreter_errors, state

__all__ = (
    "CallHandler",
    "ScrollCallback",
    "Initializer",
    "RuntimeCall",
    "RuntimeCallHandler",
    "CallbackCallHandler",
    "CallbackControlHandler",
    "CallbackCommandHandler",
    "CallbackExpansionHandler",
    "CallHandlerContainer",
    "MutableCallHandlerContainer",
    "BaseCallHandlerContainer",
    "ChoiceCallHandlerContainer",
)


logger = logging.getLogger(__name__)
T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)
AnyContextTV = t.TypeVar("AnyContextTV", bound='state.InterpreterContext')


class CallHandler(t.Protocol[T_co]):
    """
    The minimum interface required to implement a call handler.
    """

    def handle_call(self, context: AnyContextTV) -> T_co:
        """
        Handle a call. An `scrolls.interpreter.state.InterpreterContext` object will be passed in reflecting the state of the `scrolls.interpreter.run.Interpreter` for
        this call.
        """
        ...

    def __contains__(self, command_name: str) -> bool: ...


class ScrollCallback(t.Protocol[T_co]):
    """
    Protocol for callbacks passed into `scrolls.interpreter.callhandler.CallbackCallHandler` objects.

    A `ScrollCallback` is any `typing.Callable` that takes an `scrolls.interpreter.state.InterpreterContext` or subclass as its only parameter.
    """

    def __call__(self, context: AnyContextTV) -> T_co: ...


class Initializer(abc.ABC):
    """
    The base class for initializers. Initializers are used by the interpreter to set up `scrolls.interpreter.state.InterpreterContext` instances
    immediately before a script is run. Initializers are considered to implement the `CallHandler` interface, even though
    they don't actually handle calls.
    """

    @abc.abstractmethod
    def handle_call(self, context: AnyContextTV) -> None:
        """
        Initialize an `scrolls.interpreter.state.InterpreterContext` or subclass.
        """
        ...

    def __contains__(self, command_name: str) -> bool:
        return False


@dataclasses.dataclass
class RuntimeCall:
    """
    A simple runtime call that is implemented by some Scrolls code.

    .. WARNING::
        Instances of this class are created automatically by `scrolls.interpreter.callhandler.RuntimeCallHandler`.
    """

    name: str
    """The name of the call."""

    node: ast.ASTNode
    """The statement node that should be run when this call is executed."""

    params: t.Sequence[str]
    """The names of the parameters, corresponding to the names of the local variables created when this call
    is executed.
    """

    collect_param: t.Optional[str]
    """The name of the collect parameter, if any. This will always be the last parameter, and will
    collect all extra arguments fed into this call and interpret them as a string vector. In other words, this is
    the `*args` parameter, for Scrolls.
    """


class RuntimeCallHandler(t.Generic[T_co]):
    """
    A basic call handler that maps names to AST nodes.
    """

    def __init__(self) -> None:
        self.calls: t.MutableMapping[str, RuntimeCall] = {}

    def define(self, name: str, node: ast.ASTNode, params: t.Sequence[str]) -> None:
        """
        Defines a new call implemented with Scrolls code. See `RuntimeCall`.
        """
        collect_param: t.Optional[str] = None

        if params and params[-1].startswith("*"):
            collect_param = params[-1][1:]
            params = params[:-1]

        call = RuntimeCall(
            name,
            node,
            params,
            collect_param
        )

        self.calls[name] = call

    def undefine(self, name: str) -> None:
        """
        Delete a defined runtime call.
        """
        del self.calls[name]

    def handle_call(self, context: state.InterpreterContext) -> T_co:
        call = self.calls[context.call_name]

        # Arg length check
        if call.collect_param is None:
            if len(call.params) != len(context.args):
                raise interpreter_errors.InterpreterError(
                    context,
                    f"{context.call_name}: Invalid # of arguments (expected {len(call.params)})"
                )
        else:
            if len(context.args) < len(call.params) - 1:
                raise interpreter_errors.InterpreterError(
                    context,
                    f"{context.call_name}: Invalid # of arguments (expected at least {len(call.params)})"
                )

        params = list(call.params)

        if call.collect_param is None:
            args = context.args
        else:
            params.append(call.collect_param)
            collected = context.args[len(call.params):]
            args = list(context.args[:len(call.params)])
            args.append(" ".join(collected))

        # New scope must be created. We're running Scrolls code to implement this call, so it might trample
        # what's been defined otherwise. Plus, we don't want our call arguments to continue existing
        # after we're done.
        context.vars.new_scope()
        for param, arg in zip(params, args):
            context.set_var(param, arg)

        context.call_context.runtime_call = True
        try:
            # Interpret the body of the call.
            context.interpreter.interpret_statement(context, call.node)
        except interpreter_errors.InterpreterReturn:
            pass

        context.vars.destroy_scope()

        # TODO Fix typing here
        return t.cast(T_co, context.call_context.return_value)

    def __contains__(self, command_name: str) -> bool:
        return command_name in self.calls


class CallbackCallHandler(t.Generic[T_co]):
    """
    A basic call handler that uses `typing.Callable` (`ScrollCallback`) to
    implement a call handler.
    """

    def __init__(self) -> None:
        self.calls: t.MutableMapping[str, ScrollCallback[T_co]] = {}
        self.aliases: t.MutableMapping[str, str] = {}

    def add_call(self, name: str, command: ScrollCallback[T_co]) -> None:
        """
        Add a call.
        """
        self.calls[name] = command

    def add_alias(self, alias: str, name: str) -> None:
        """Adds an alias for the named call. The call can then be executed by either it's real name or any of the
        defined aliases."""
        self.aliases[alias] = name

    def remove_call(self, name: str) -> None:
        """Remove a call. Note that this also removes all of its associated aliases."""
        del self.calls[name]

        # Delete all aliases associated with the name.
        for key, value in self.aliases.items():
            if value == name:
                del self.aliases[key]

    def get_callback(self, name: str) -> ScrollCallback[T_co]:
        """Get the callback for a call."""
        if name in self.calls:
            return self.calls[name]

        return self.calls[self.aliases[name]]

    def handle_call(self, context: state.InterpreterContext) -> T_co:
        return self.get_callback(context.call_name)(context)

    def __contains__(self, command_name: str) -> bool:
        logger.debug(f"{self.__class__.__qualname__}: __contains__({command_name})")
        return (
                command_name in self.calls or
                command_name in self.aliases
        )


CallbackCommandHandler = CallbackCallHandler[None]
"""A basic command handler, shortcut for `CallbackCallHandler[None]`."""

CallbackControlHandler = CallbackCallHandler[None]
"""A basic control handler, shortcut for `CallbackCallHandler[None]`."""

CallbackExpansionHandler = CallbackCallHandler[str]
"""A basic expansion handler, shortcut for `CallbackCallHandler[str]`."""


class CallHandlerContainer(t.Protocol[T_co]):
    """
    A read-only `CallHandler` container.
    """

    def get(self, name: str) -> CallHandler[T_co]: ...

    """Gets a call handler by name."""

    def get_for_call(self, name: str) -> CallHandler[T_co]: ...

    """Gets a call handler for the named call."""

    def __iter__(self) -> t.Iterator[CallHandler[T_co]]: ...


class MutableCallHandlerContainer(CallHandlerContainer[T], t.Protocol[T]):
    """
    A mutable `CallHandler` container.
    """

    def add(self, handler: CallHandler[T], name: str = "") -> None: ...

    """Add a call handler to this container.

    If `name` is not specified, then a unique name should be generated. The specific name generated is up to the
    implementor.
    """

    def remove(self, handler: t.Union[CallHandler[T], str]) -> None: ...

    """Remove a call handler from this container."""


class BaseCallHandlerContainer(t.Generic[T]):
    """
    Generic container for `CallHandler` implementors.
    """

    def __init__(self) -> None:
        self._handlers: t.MutableMapping[str, CallHandler[T]] = {}

    def add(self, handler: CallHandler[T], name: str = "") -> None:
        """Add a call handler to this container.

        If `name` is not specified, then a unique name will be generated through `uuid.uuid4`.
        """
        if not name:
            name = str(uuid.uuid4())

        logger.debug(f"Register call handler type {handler.__class__.__qualname__} name {name}")
        self._handlers[name] = handler

    def add_all(self, handlers: t.Sequence[CallHandler[T]]) -> None:
        """Shortcut, adds all handlers in a list at once."""
        for handler in handlers:
            self.add(handler)

    def find(self, handler: t.Union[CallHandler[T], str]) -> tuple[str, CallHandler[T]]:
        """Find a call handler.

        Args:
            handler: The handler to search for. It may be a CallHandler object, or the name of the handler to search for.

        Returns:
            A `tuple` of the form `(name, call_handler)`.
        """
        if isinstance(handler, str):
            return handler, self._handlers[handler]
        else:
            for k, v in self._handlers.items():
                if v is handler:
                    return k, v

            raise KeyError(repr(handler))

    def remove(self, handler: t.Union[CallHandler[T], str]) -> None:
        """Remove a call handler from this container."""
        k, v = self.find(handler)
        del self._handlers[k]

    def get(self, name: str) -> CallHandler[T]:
        """Gets a call handler by name."""
        return self._handlers[name]

    def get_for_call(self, name: str) -> CallHandler[T]:
        """
        Get the handler for a given command name.
        """
        logger.debug(f"get_for_call: {name}")
        for handler in self._handlers.values():
            if name in handler:
                return handler

        raise KeyError(name)

    def __iter__(self) -> t.Iterator[CallHandler[T]]:
        yield from self._handlers.values()


class ChoiceCallHandlerContainer(t.Generic[T]):
    """
    A call handler tries to handle a call with a sequence of call handler containers, one after another.
    """

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
        logger.debug(f"ChoiceCallHandlerContainer: get_for_call {name}")
        for container in self.containers:
            try:
                return container.get_for_call(name)
            except KeyError:
                logger.debug(f"fail on {container.__class__.__qualname__}")
                pass

        raise KeyError(name)

    def __iter__(self) -> t.Iterator[CallHandler[T]]:
        for container in self.containers:
            yield from container
