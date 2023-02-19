"""
Data structures used to implement the interpreter state.
"""

import dataclasses
import logging
import typing as t

from .. import ast

__all__ = (
    "ArgSourceMap",
    "CallContext",
    "VarScope",
    "ScopedVarStore",
)


logger = logging.getLogger(__name__)
T = t.TypeVar("T")


class ArgSourceMap(dict[int, T], t.Generic[T]):
    """A utility class that maps argument numbers to some source.

    The main purpose of this container is to map call arguments to the `scrolls.ast.syntax.ASTNode` they came from.
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

    - `scrolls.interpreter.state.InterpreterContext.call_stack`
    - `scrolls.interpreter.state.InterpreterContext.call_context`

    <br/>

    .. NOTE::
        Control structures such as `!for`, `!while`, etc., are also considered calls, but they do not create
        a new `scrolls.interpreter.struct.VarScope`. So, call contexts and variable scopes are considered separately.
    """

    call_name: str
    """The name of this call."""

    args: t.Sequence[str]
    """The arguments passed into this call."""

    arg_nodes: ArgSourceMap[ast.ASTNode]
    """A map of argument indices to the `scrolls.ast.syntax.ASTNode` they came from."""

    control_node: t.Optional[ast.ASTNode] = None
    """If this call is a control call, this will contain the call's `scrolls.ast.syntax.ASTNode` parameter."""

    return_value: t.Optional[t.Any] = None
    """The return value set by a runtime call."""

    runtime_call: bool = False
    """A runtime call is a call defined while the interpreter is running, such as through `!def`."""

    else_signal: bool = False
    """
    Read by the `!else` builtin. If True, the next `!else` called in the current
    context will execute, and set the signal back to False. From within a control
    call, this should be set through `scrolls.interpreter.state.InterpreterContext.parent_call_context`.
    """

    _id_format: t.ClassVar[str] = "{id:<{id_size}}"
    _str_format: t.ClassVar[str] = "{flags:<5} {name_and_args}"
    _trace_format: t.ClassVar[str] = f"{_id_format} {_str_format}"
    _id_title: t.ClassVar[str] = "ID"

    @classmethod
    def _min_id_size(cls, id_size: int) -> int:
        return max(id_size, len(cls._id_title))

    @classmethod
    def trace_banner(cls, id_size: int) -> str:
        """
        Gets a banner string for a backtrace. Should be followed by a list of
        `trace_str` outputs.

        Args:
            id_size: The size in characters of the ID field.
        """
        return cls._trace_format.format(
            id=cls._id_title,
            id_size=cls._min_id_size(id_size),
            flags="FLAGS",
            name_and_args="NAME+ARGS"
        )

    def trace_str(self, id: int, id_size: int) -> str:
        """
        Gets a string representation of this call context for the purposes
        of printing a stack trace.

        Args:
            id: The numeric ID of the trace item.
            id_size: The size in characters of the ID field.
        """
        id_str = self._id_format.format(id=id, id_size=self._min_id_size(id_size))
        return f"{id_str} {self}"

    def __str__(self) -> str:
        flags = [
            "!" if self.control_node is not None else "-",
            "e" if self.else_signal else "-",
            "r" if self.runtime_call else "-"
        ]

        name_and_args = [
            f"\"{self.call_name}\"",
            *[f"\"{arg}\"" for arg in self.args]
        ]

        return self._str_format.format(
            flags="".join(flags),
            name_and_args=" ".join(name_and_args)
        )


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
    `scrolls.interpreter.struct.CallContext`) use scoped variable stores to allow the definition of local variables in call defs without
    stepping on existing variables.

    .. IMPORTANT::
        Calls implemented in Python do not enter a new variable scope by default. You typically won't need to enter
        a new scope unless you run Scrolls code during a call, i.e. for control calls, and runtime-defined calls.

        Most control calls, such as `while`, `for`, `if`, etc. do not need to define a new variable scope. The option
        is available if desired. See the source code of `scrolls.interpreter.callhandler.RuntimeCallHandler.handle_call` for an example of defining
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
