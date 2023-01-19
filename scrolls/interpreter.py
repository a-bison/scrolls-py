"""
The interpreter implementation.

.. include:: ./pdoc/interpreter.md
"""

import abc
import dataclasses
import logging
import pathlib
import types
import typing as t
import uuid

from . import ast, errors

__all__ = (
    "ArgSourceMap",
    "CallContext",
    "ScopedVarStore",
    "VarScope",
    "InterpreterContext",
    "CallHandler",
    "CallbackCommandHandler",
    "CallbackControlHandler",
    "CallbackExpansionHandler",
    "Interpreter",
    "InterpreterError",
    "InternalInterpreterError",
    "ScrollCallback",
    "Initializer",
    "CallHandlerContainer",
    "MutableCallHandlerContainer",
    "BaseCallHandlerContainer",
    "RuntimeCallHandler",
    "CallbackCallHandler",
    "InterpreterStop",
    "InterpreterReturn",
    "RuntimeCall",
    "ChoiceCallHandlerContainer"
)

logger = logging.getLogger(__name__)

T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)
AnyContextTV = t.TypeVar("AnyContextTV", bound='InterpreterContext')


class ArgSourceMap(dict[int, T], t.Generic[T]):
    """A utility class that maps argument numbers to some source.

    The main purpose of this container is to map call arguments to the `scrolls.ast.ASTNode` they came from.
    This class is typically used to accurately point to a node in the case of a call error.

    Usage
    ```py
    # Note: SourceClass is just an example here.
    sources: typing.Sequence[SourceClass] = get_some_sources()
    source_map: ArgSourceMap[SourceClass] = ArgSourceMap()

    args = []
    for source in sources:
        args_from_source = source.get_args()
        source_map.add_args(args_from_source, source)

    # Now, you can use an arg number to look up which SourceClass it came from.
    arg_2_src = source_map[2]
    ```
    """

    def __init__(self, *args: t.Any, **kwargs: t.Any):
        super().__init__(*args, **kwargs)

        self.count = 0

    def add_args(self, args: t.Sequence, source: T) -> None:
        """
        Add an `(args, source)` pair to this mapping. See usage example above.
        """
        for i, _ in enumerate(args):
            self[i + self.count] = source

        self.count += len(args)


@dataclasses.dataclass
class CallContext:
    """
    The context of a call. Contains all information necessary to run a call. Under normal circumstances,
    you won't need to create instances of this yourself. Instead access instances through:

    - `InterpreterContext.call_stack`
    - `InterpreterContext.call_context`

    <br/>

    .. NOTE::
        Control structures such as `!for`, `!while`, etc., are also considered calls, but they do not create
        a new `VarScope`. So, call contexts and variable scopes are considered separately.
    """

    call_name: str
    """The name of this call."""

    args: t.Sequence[str]
    """The arguments passed into this call."""

    arg_nodes: ArgSourceMap[ast.ASTNode]
    """A map of argument indices to the `scrolls.ast.ASTNode` they came from."""

    control_node: t.Optional[ast.ASTNode] = None
    """If this call is a control call, this will contain the call's `scrolls.ast.ASTNode` parameter."""

    return_value: t.Optional[t.Any] = None
    """The return value set by a runtime call."""

    runtime_call: bool = False
    """A runtime call is a call defined while the interpreter is running, such as through `!def`."""

    else_signal: bool = False
    """
    Read by the `!else` builtin. If True, the !else control call executes
    its body. If False, !else calls are skipped. Should not be set manually,
    use the 
    """

class VarScope:
    """
    A variable scope. See `ScopedVarStore`.
    """
    def __init__(self) -> None:
        self.vars: t.MutableMapping[str, str] = {}
        """The local variables defined in this scope.
        
        .. NOTE::
            Generally this should not be modified directly, use `ScopedVarStore.set_var` instead.
        """

        self.nonlocals: t.MutableMapping[str, bool] = {}
        """Nonlocal variables defined in this scope.
        
        If a variable is declared nonlocal, attempts to read/write it will go to the enclosing scope.
        
        .. NOTE::
            Generally this should not be modified directly, use `ScopedVarStore.declare_nonlocal` instead.
        """

        self.globals: t.MutableMapping[str, bool] = {}
        """Global variables defined in this scope.
        
        If a variable is declared global, attempts to read/write it will go to the global (top level) variable scope.
        
        .. NOTE::
            Generally this should not be modified directly, use `ScopedVarStore.declare_global` instead.
        """


class ScopedVarStore:
    """
    A variable store divided into a stack of key-value pairs.

    This class is used to implement the concept of local vs global variables in scrolls. Runtime calls (see
    `CallContext`) use scoped variable stores to allow the definition of local variables in call defs without
    stepping on existing variables.

    .. IMPORTANT::
        Calls implemented in Python do not enter a new variable scope by default. You typically won't need to enter
        a new scope unless you run Scrolls code during a call, i.e. for control calls, and runtime-defined calls.

        Most control calls, such as `while`, `for`, `if`, etc. do not need to define a new variable scope. The option
        is available if desired. See the source code of `RuntimeCallHandler.handle_call` for an example of defining
        a new scope.
    """
    def __init__(self) -> None:
        self.scopes: t.MutableSequence[VarScope] = []
        """The `VarScope` stack. Later indices are deeper scopes. `scopes[0]` is the global scope, which is always available."""

        self.new_scope()  # There should always be one scope.

    def new_scope(self) -> None:
        """
        Push a new scope onto the stack.
        """
        self.scopes.append(VarScope())

    def destroy_scope(self) -> None:
        """
        Destroy the current scope and return to the last one. This will delete all local variables defined in the current
        scope.
        """
        if len(self.scopes) == 1:
            # there should always be at least one scope
            raise ValueError("There must be at least one scope.")

        self.scopes.pop()

    def declare_nonlocal(self, name: str) -> None:
        """
        Declare a variable as nonlocal. This means that all attempts to read/write the variable will automatically
        go to the enclosing scope.
        """
        self.current_scope.nonlocals[name] = True

    def declare_global(self, name: str) -> None:
        """
        Declare a variable as global. This means all attempts to read/write the variable will automatically go to
        the global scope.
        """
        self.current_scope.globals[name] = True

    def search_scope(self, name: str, scopes: t.Sequence[VarScope], read_search: bool = False) -> VarScope:
        """
        Using a variable name, search up the scope stack for something to read/write. This search will honor nonlocal
        and global declarations made for all scopes.

        Args:
            name: The name of the variable to search for.

            scopes: The scopes to search. Typically, this will be `ScopedVarStore.scopes`.

            read_search: Must be `True` if no writes will be performed on the scope you're searching for.
            Adds additional logic that reads the global store as a fallback if a defined value could not be found
            after searching up the stack.

        Raises:
            KeyError: If an appropriate scope could not be found.
        """
        scopes = list(scopes)
        scope = scopes[-1]

        while scopes:
            scope = scopes.pop()

            if name in scope.globals:
                # If global, immediately go to the highest scope
                return scopes[0] if scopes else scope

            if name in scope.nonlocals:
                # If nonlocal, go to the enclosing scope.
                continue

            # Just break as soon as we step off global/nonlocal references.
            break

        if read_search:
            # Do a little bit of extra logic for a read search. If we can't find a value in the
            # current scope, try globals as a fallback.
            if name in scope.vars:
                return scope
            elif scopes and name in scopes[0].vars:
                return scopes[0]
            else:
                raise KeyError(name)

        return scope

    def get_scope_for_read(self, name: str) -> VarScope:
        """Shortcut for `ScopedVarStore.search_scope(..., read_search=True)`

        See Also: `ScopedVarStore.search_scope`
        """
        return self.search_scope(name, self.scopes, read_search=True)

    def get_scope_for_write(self, name: str) -> VarScope:
        """Shortcut for `ScopedVarStore.search_scope(..., read_search=False)`

        See Also: `ScopedVarStore.search_scope`
        """
        return self.search_scope(name, self.scopes, read_search=False)

    @property
    def current_scope(self) -> VarScope:
        """The current scope."""
        return self.scopes[-1]

    def get_var(self, name: str) -> str:
        """Get a variable from this store, following all nonlocal and global declarations."""
        return self.get_scope_for_read(name).vars[name]

    def set_var(self, name: str, value: str) -> None:
        """Set a variable in this store, following all nonlocal and global declarations."""
        try:
            scope = self.get_scope_for_write(name)
            scope.vars[name] = value
        except KeyError:
            self.current_scope.vars[name] = value

    def del_var(self, name: str) -> None:
        """Delete a variable from this store, following all nonlocal and global declarations."""
        try:
            scope = self.get_scope_for_write(name)
            del scope.vars[name]
        except KeyError:
            del self.current_scope.vars[name]


class InterpreterContext:
    """
    Base class for the command interpreter context. Contains all state information for the `Interpreter`.
    This is also the main interface plugin writers will use to interact with the interpreter, and is passed to all
    `CallHandler` implementations.
    """
    def __init__(self, *_: t.Any):
        self._current_node: t.Optional[ast.ASTNode] = None
        self._call_context: t.Optional[CallContext] = None
        self._interpreter: t.Optional[Interpreter] = None
        self._vars = ScopedVarStore()

        self.statement_count = 0
        """The number of statements that have been run by the interpreter so far."""

        self._call_stack: t.MutableSequence[CallContext] = []
        self._command_handlers: BaseCallHandlerContainer[None] = BaseCallHandlerContainer()
        self._expansion_handlers: BaseCallHandlerContainer[str] = BaseCallHandlerContainer()

        self._open_files: t.MutableMapping[int, t.IO[str]] = {}
        self._fid = 0

    @property
    def vars(self) -> ScopedVarStore:
        """The variable store."""
        return self._vars

    def set_var(self, name: str, value: str) -> None:
        """Set a variable."""
        self.vars.set_var(name, value)

    def del_var(self, name: str) -> None:
        """Delete a variable."""
        self.vars.del_var(name)

    def get_var(self, name: str) -> str:
        """Get a variable."""
        return self.vars.get_var(name)

    def open_file(self, path: str, mode: str) -> int:
        """
        Opens a file for this context.

        Returns:
             A numeric file ID that should be used in other `*_file` functions
             for `InterpreterContext`.
        """
        p = pathlib.Path(path)

        if not p.exists():
            raise InterpreterError(
                self,
                f"{path} does not exist"
            )

        if not p.is_file():
            raise InterpreterError(
                self,
                f"{path} is not a file"
            )

        # do not allow binary mode for now
        mode = mode.replace("b", "")

        f = open(p, mode)
        self._open_files[self._fid] = f
        used_fid = self._fid
        self._fid += 1

        logger.debug(f"Opened file: {path}")

        return used_fid

    def close_file(self, fid: int) -> None:
        """
        Closes a file for this context.
        """
        if fid not in self._open_files:
            raise InterpreterError(
                self,
                f"file already closed, or not open (fid {fid})"
            )

        self._open_files[fid].close()
        del self._open_files[fid]

    def get_file(self, fid: int) -> t.IO[str]:
        """
        Gets an open file for this context.
        """
        if fid not in self._open_files:
            raise InterpreterError(
                self,
                f"file already closed, or not open (fid {fid})"
            )

        return self._open_files[fid]

    @property
    def runtime_commands(self) -> 'BaseCallHandlerContainer[None]':
        """The call handler container for runtime command handlers. Runtime commands are defined while the interpreter
        is running, i.e. through the `!def` directive or similar. Runtime commands

        For any command handler added to this container, all commands defined within it:

        - **Should** always perform their work in their own variable scope. See `ScopedVarStore.new_scope`.
        - **Must** set the `CallContext.runtime_call` parameter to `True`.
        - **Must** cease executing if an `InterpreterStop` or `InterpreterReturn` is raised.
        """
        return self._command_handlers

    @property
    def runtime_expansions(self) -> 'BaseCallHandlerContainer[str]':
        """Same as `InterpreterContext.runtime_commands`, but for expansion calls.

        Runtime expansions follow the same requirements as commands, plus:

        - **Must** set the `CallContext.return_value` parameter upon call completion.
        - **Must** catch `InterpreterReturn` and set the return value on this exception.
        """
        return self._expansion_handlers

    @property
    def interpreter(self) -> 'Interpreter':
        """
        The interpreter running using this context.

        Raises:
            InternalInterpreterError: If this property is not initialized.
        """
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
        """
        The current `scrolls.ast.ASTNode` being interpreted.

        Raises:
            InternalInterpreterError: If there is no current node.
        """
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
        """
        The call stack. Used primarily for tracking return values in runtime calls, and feeding
        call information to `CallHandler` implementations. Variables scopes are tracked separately.
        See `InterpreterContext.vars`.

        .. WARNING::
            This stack does not contain the current call. See `InterpreterContext.call_context` for that.
        """
        return self._call_stack

    @property
    def call_context(self) -> CallContext:
        """
        The current call context.
        """
        self._call_check()
        return t.cast(CallContext, self._call_context)

    @property
    def parent_call_context(self) -> CallContext:
        """
        Get the context of the call that called the current one. Can be used to
        influence signals in the parent context.
        """
        self._call_check()
        if not self.call_stack:
            raise InternalInterpreterError(
                self, f"Cannot get parent of base call \"{self.call_context.call_name}\""
            )

        return self.call_stack[-1]

    @property
    def call_name(self) -> str:
        """
        The name of the current call.
        """
        self._call_check()
        return self.call_context.call_name

    @property
    def args(self) -> t.Sequence[str]:
        """
        The argments passed into the current call.
        """
        self._call_check()
        return self.call_context.args

    @property
    def arg_nodes(self) -> ArgSourceMap[ast.ASTNode]:
        """
        The `scrolls.ast.ASTNode` instances the current call's arguments came from.
        """
        self._call_check()
        return self.call_context.arg_nodes

    @property
    def control_node(self) -> ast.ASTNode:
        """
        If the current context is a control call, this will contain the `scrolls.ast.ASTNode` parameter passed into it.

        Raises:
            InternalInterpreterError: If the current context is not a call.
        """
        if self.call_context.control_node is None:
            raise InternalInterpreterError(
                self, "Current context is not a control call."
            )

        return self.call_context.control_node

    def set_base_call(
        self
    ) -> None:
        """
        Sets the current call context to the base call context for top level code.

        .. WARNING::
            Provided for advanced usage, this is usually done automatically. Typical users will never need to call this.
        """
        logger.debug("set_base_call")
        self._call_context = CallContext(
            "__main__",
            [],
            ArgSourceMap(),
            None
        )

    def set_call(
        self,
        command: str,
        args: t.Sequence[str],
        arg_nodes: ArgSourceMap[ast.ASTNode],
        control_node: t.Optional[ast.ASTNode] = None
    ) -> None:
        """
        Sets the current call context, overwriting whatever was previously current. If you want to preserve the
        current context for later use, see `InterpreterContext.push_call`

        .. WARNING::
            Provided for advanced usage, this is usually done automatically. Typical users will never need to call this.
        """
        self._call_context = CallContext(
            command,
            args,
            arg_nodes,
            control_node
        )

    def push_call(self) -> None:
        """
        Duplicate the current call context and push it onto the call stack. Should be followed up with
        `InterpreterContext.set_call` to create a new context.

        .. WARNING::
            Provided for advanced usage, this is usually done automatically. Typical users will never need to call this.
        """
        self._call_check()
        self._call_stack.append(self.call_context)

    def pop_call(self) -> None:
        """
        Destroy the current call context, and replace it with the first context on the call stack.

        .. WARNING::
            Provided for advanced usage, this is usually done automatically. Typical users will never need to call this.

        Raises:
            InternalInterpreterError: If not calls have been pushed.
        """
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
        """
        Sets the return value in the first runtime call found in the stack.

        Raises:
            InterpreterError: If outside a call context, no call stack, or no runtime call contexts found.
        """
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
    def handle_call(self, context: AnyContextTV) -> T_co:
        """
        Handle a call. An `InterpreterContext` object will be passed in reflecting the state of the `Interpreter` for
        this call.
        """
        ...

    def __contains__(self, command_name: str) -> bool: ...


class ScrollCallback(t.Protocol[T_co]):
    """
    Protocol for Callbacks passed into CallbackCallHandlers.

    A `ScrollCallback` is any `typing.Callable` that takes an `InterpreterContext` or subclass as its only parameter.
    """
    def __call__(self, context: AnyContextTV) -> T_co: ...


class Initializer(abc.ABC):
    """
    The base class for initializers. Initializers are used by the interpreter to set up `InterpreterContext` instances
    immediately before a script is run. Initializers are considered to implement the `CallHandler` interface, even though
    they don't actually handle calls.
    """

    @abc.abstractmethod
    def handle_call(self, context: AnyContextTV) -> None:
        """
        Initialize an `InterpreterContext` or subclass.
        """
        ...

    def __contains__(self, command_name: str) -> bool:
        return False


@dataclasses.dataclass
class RuntimeCall:
    """
    A simple runtime call that is implemented by some Scrolls code.

    .. WARNING::
        Instances of this class are created automatically by `RuntimeCallHandler`.
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

    def handle_call(self, context: InterpreterContext) -> T_co:
        call = self.calls[context.call_name]

        # Arg length check
        if call.collect_param is None:
            if len(call.params) != len(context.args):
                raise InterpreterError(
                    context,
                    f"{context.call_name}: Invalid # of arguments (expected {len(call.params)})"
                )
        else:
            if len(context.args) < len(call.params) - 1:
                raise InterpreterError(
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
        except InterpreterReturn:
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

    def handle_call(self, context: InterpreterContext) -> T_co:
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


class InterpreterError(errors.PositionalError):
    """
    A generic interpreter error. All interpreter errors should subclass this.
    """
    def __init__(self, ctx: InterpreterContext, message: str):
        self.ctx = ctx

        if self.ctx.current_node.has_token():
            tok = self.ctx.current_node.tok
            super().__init__(
                tok.line,
                tok.position,
                tok.tokenizer.stream.history(),
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
    Raised when a call cannot be found.
    """
    def __init__(self, ctx: InterpreterContext, call_type: str, call_name: str):
        self.call = call_name
        message = f"{call_type.capitalize()} '{call_name}' not found."
        super().__init__(
            ctx, message
        )


class InternalInterpreterError(InterpreterError):
    """
    Raised on critical interpreter errors that are usually the result of bugs.
    """
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
    The interpreter implementation for Scrolls. Configure through the `*_handlers` properties. Or, for a more organized
    configuration, see `scrolls.containers.DecoratorInterpreterConfig`.

    Args:
        context_cls: The `InterpreterContext` class to use when automatically instantiating new context objects.
            Must be `InterpreterContext` or a subclass of it.

        statement_limit: The number of statements allowed while executing a script. This is counted in the
            `InterpreterContext` object for a given run. If the number of executed statements exceeds this, an
            `InterpreterError` will be raised. If set to zero, then there is no statement limit.

        call_depth_limit: The number of levels deep the call stack is allowed to go. This is used to prevent
            denial of service through infinite recursion. If zero, then call depth is unlimited.
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
        """
        The `InterpreterContext` class to use when automatically instantiating new context objects.
        Must be `InterpreterContext` or a subclass of it.
        """

        self.statement_limit = statement_limit
        self.call_depth_limit = call_depth_limit

    def over_statement_limit(self, context: InterpreterContext) -> bool:
        """
        Utility function. Checks whether the passed context has exceeded the statement limit set for this interpreter.
        """
        if self.statement_limit == 0:
            return False
        else:
            return context.statement_count > self.statement_limit

    def over_call_depth_limit(self, context: InterpreterContext) -> bool:
        """
        Utility function. Checks whether the passed context has exceeded the call stack depth limit set for this
        interpreter.
        """
        if self.call_depth_limit == 0:
            return False
        else:
            return len(context.call_stack) > self.call_depth_limit

    @property
    def command_handlers(self) -> BaseCallHandlerContainer[None]:
        """The container of command handlers for this interpreter."""
        return self._command_handlers

    @property
    def control_handlers(self) -> BaseCallHandlerContainer[None]:
        """The container of control handlers for this interpreter."""
        return self._control_handlers

    @property
    def expansion_handlers(self) -> BaseCallHandlerContainer[str]:
        """The container of expansion handlers for this interpreter."""
        return self._expansion_handlers

    @property
    def initializers(self) -> BaseCallHandlerContainer[None]:
        """The container of `Initializer` instances for this interpreter."""
        return self._initializers

    def apply_initializers(self, context: InterpreterContext) -> None:
        """Apply this interpreter's context initializers to the given context object."""
        for init in self.initializers:
            init.handle_call(context)

    def run(
        self,
        script: str,
        context: t.Optional[InterpreterContext] = None,
        consume_rest_triggers: t.Mapping[str, int] = types.MappingProxyType({})
    ) -> InterpreterContext:
        """Run a Scrolls script.

        Args:
            script: The script to run.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.
            consume_rest_triggers: A mapping of triggers for the CONSUME_REST parsing feature.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `InterpreterContext` instance.
        """
        tokenizer = ast.Tokenizer(script, consume_rest_triggers)
        tree = ast.parse_scroll(tokenizer)
        return self.interpret_ast(tree, context)

    def init_context(self, context: InterpreterContext) -> None:
        """
        Initialize a context for this interpreter.
        """
        context.interpreter = self
        context.set_base_call()
        self.apply_initializers(context)

    def run_statement(
        self,
        statement: t.Union[str, ast.Tokenizer],
        context: t.Optional[InterpreterContext] = None,
    ) -> InterpreterContext:
        """Run a single Scrolls statement.

        Args:
            statement: The statement to run. Must be either a string, or a tokenizer populated with a valid Scrolls
                statement.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `InterpreterContext` instance.
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
        on_error: t.Optional[t.Callable[[errors.ScrollError], None]] = None
    ) -> None:
        """
        Drop into a REPL (read eval print loop).

        Args:
            on_error: A function to call when an error occurs. If `None`,
                      errors will stop the REPL.
        """
        stream = ast.REPLStream()
        tokenizer = ast.Tokenizer(stream)
        context = self.context_cls()
        self.init_context(context)

        while True:
            try:
                statement_node = ast.parse_statement(tokenizer)
                stream.set_statement()

                self.interpret_statement(context, statement_node)
            except InterpreterStop:
                return
            except InterpreterReturn:
                e = InterpreterError(
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
            except errors.ScrollError as e:
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
        Returns a JSON-formatted string showing the full `scrolls.ast.ASTNode` structure of a parsed script, including
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
        context: t.Optional[InterpreterContext] = None
    ) -> InterpreterContext:
        """
        Interprets a full AST structure.

        Args:
            tree: The AST to interpret.
            context: Optional. If no context is specified, then an instance of `Interpreter.context_cls` is created
                automatically. Otherwise, the passed context object will be used.

        Returns:
            The context used to execute the script. If `context` was not None, `context` will be returned. Otherwise,
            it will be the automatically created `InterpreterContext` instance.
        """
        if context is None:
            context = self.context_cls(tree.root)

        self.init_context(context)

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
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.ROOT`."""
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

        Args:
            call_handler_container: The call handler container to check for call handlers.
            context: The interpreter context.
            node: The AST node to interpret.
            expected_node_type: The type of AST node to be expected.
            pass_control_node: Whether to pass `node.children[2]` into the control parameter of a call. Currently,
                this only applies to control calls. See `InterpreterContext.control_node`.

        Returns:
            The result of the call, if any.

        Related:
            `Interpreter.interpret_command` `Interpreter.interpret_control` `Interpreter.interpret_expansion_call`
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
            context.pop_call()

            raise

        context.pop_call()

        return result

    def interpret_control(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.CONTROL_CALL`."""
        self.interpret_call(
            self.control_handlers,
            context,
            node,
            ast.ASTNodeType.CONTROL_CALL,
            pass_control_node=True
        )

    def interpret_command(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.COMMAND_CALL`."""
        self.interpret_call(
            ChoiceCallHandlerContainer(
                context.runtime_commands,
                self.command_handlers
            ),
            context,
            node,
            ast.ASTNodeType.COMMAND_CALL
        )

    def interpret_variable_reference(self, context: InterpreterContext, node: ast.ASTNode) -> str:
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.EXPANSION_VAR`."""
        context.current_node = node

        var_name = " ".join(self.interpret_string_or_expansion(context, node.children[0]))
        try:
            return context.get_var(var_name)
        except KeyError:
            raise InterpreterError(
                context, f"No such variable {var_name}."
            )

    def interpret_expansion_call(self, context: InterpreterContext, node: ast.ASTNode) -> str:
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.EXPANSION_CALL`."""
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
        """Utility. Interprets an expansion child node, which may be either `scrolls.ast.ASTNodeType.EXPANSION_VAR` or
        `scrolls.ast.ASTNodeType.EXPANSION_CALL`.
        """
        context.current_node = node

        if node.type == ast.ASTNodeType.EXPANSION_VAR:
            return self.interpret_variable_reference(context, node)
        elif node.type == ast.ASTNodeType.EXPANSION_CALL:
            return self.interpret_expansion_call(context, node)
        else:
            raise InternalInterpreterError(
                context,
                f"Bad expansion node type {node.type.name}"
            )

    def interpret_expansion(self, context: InterpreterContext, node: ast.ASTNode) -> t.Sequence[str]:
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.EXPANSION`."""
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
        """Utility. Interprets call names and arguments, which may be either `scrolls.ast.ASTNodeType.STRING` or
        `scrolls.ast.ASTNodeType.EXPANSION`
        """

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
        """Interpret an `scrolls.ast.ASTNode` of type `scrolls.ast.ASTNodeType.BLOCK`."""
        context.current_node = node

        for sub_statement in context.current_node.children:
            self.interpret_statement(context, sub_statement)

    def interpret_statement(self, context: InterpreterContext, node: ast.ASTNode) -> None:
        """Utility. Interprets Scrolls statements, which may be `scrolls.ast.ASTNodeType.CONTROL_CALL`,
        `scrolls.ast.ASTNodeType.COMMAND_CALL`, or `scrolls.ast.ASTNodeType.BLOCK`.

        More often than not, this is the function that control calls will use to run the statement passed to
        `InterpreterContext.control_node`. See `scrolls.builtins.BuiltinControlHandler` for examples.
        """
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
