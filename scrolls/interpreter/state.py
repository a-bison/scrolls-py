"""
Implementation of interpreter state. Variables, open files, call stack, etc.
"""

import logging
import math
import pathlib
import typing as t

from .. import ast
from . import callhandler, errors, struct

if t.TYPE_CHECKING:
    from . import run

__all__ = (
    "InterpreterContext",
)


logger = logging.getLogger(__name__)
T = t.TypeVar("T")


class InterpreterContext:
    """
    Base class for the command interpreter context. Contains all state information for the `scrolls.interpreter.run.Interpreter`.
    This is also the main interface plugin writers will use to interact with the interpreter, and is passed to all
    `scrolls.interpreter.callhandler.CallHandler` implementations.
    """

    def __init__(self, *_: t.Any):
        self._current_node: t.Optional[ast.ASTNode] = None
        self._call_context: t.Optional[struct.CallContext] = None
        self._interpreter: t.Optional['run.Interpreter'] = None
        self._vars = struct.ScopedVarStore()

        self.statement_count = 0
        """The number of statements that have been run by the interpreter so far."""

        self._call_stack: t.MutableSequence[struct.CallContext] = []

        # Handlers for calls defined at runtime
        self._runtime_command_handlers: callhandler.MutableCallHandlerContainer[None] = callhandler.BaseCallHandlerContainer()
        self._runtime_expansion_handlers: callhandler.MutableCallHandlerContainer[str] = callhandler.BaseCallHandlerContainer()

        # Combined handlers that check both runtime and static calls
        self._all_command_handlers: t.Optional[callhandler.CallHandlerContainer[None]] = None
        self._all_expansion_handlers: t.Optional[callhandler.CallHandlerContainer[str]] = None

        self._open_files: t.MutableMapping[int, t.IO[str]] = {}
        self._fid = 0

    @property
    def vars(self) -> struct.ScopedVarStore:
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
             for `scrolls.interpreter.state.InterpreterContext`.
        """
        p = pathlib.Path(path)

        if not p.exists():
            raise errors.InterpreterError(
                self,
                f"{path} does not exist"
            )

        if not p.is_file():
            raise errors.InterpreterError(
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
            raise errors.InterpreterError(
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
            raise errors.InterpreterError(
                self,
                f"file already closed, or not open (fid {fid})"
            )

        return self._open_files[fid]

    @property
    def runtime_commands(self) -> 'callhandler.MutableCallHandlerContainer[None]':
        """The call handler container for runtime command handlers. Runtime commands are defined while the interpreter
        is running, i.e. through the `!def` directive or similar.

        For any command handler added to this container, all commands defined within it:

        - **Should** always perform their work in their own variable scope. See `scrolls.interpreter.struct.ScopedVarStore.new_scope`.
        - **Must** set the `scrolls.interpreter.struct.CallContext.runtime_call` parameter to `True`.
        - **Must** cease executing if an `scrolls.interpreter.errors.InterpreterStop` or `scrolls.interpreter.errors.InterpreterReturn` is raised.
        """
        return self._runtime_command_handlers

    @property
    def runtime_expansions(self) -> 'callhandler.MutableCallHandlerContainer[str]':
        """Same as `scrolls.interpreter.state.InterpreterContext.runtime_commands`, but for expansion calls.

        Runtime expansions follow the same requirements as commands, plus:

        - **Must** set the `scrolls.interpreter.struct.CallContext.return_value` parameter upon call completion.
        - **Must** catch `scrolls.interpreter.errors.InterpreterReturn` and set the return value on this exception.
        """
        return self._runtime_expansion_handlers

    @property
    def all_commands(self) -> 'callhandler.CallHandlerContainer[None]':
        """
        The call handler container for all commands currently defined at execution
        time, including all static commands.

        Plugins wishing to programmatically call commands should use this.

        Raises:
            scrolls.interpreter.errors.InternalInterpreterError: If this property is not initialized.
        """
        if self._all_command_handlers is None:
            raise errors.InternalInterpreterError(
                self, "Bad context: _all_command_handlers not initialized."
            )

        return self._all_command_handlers

    @property
    def all_expansions(self) -> 'callhandler.CallHandlerContainer[str]':
        """
        The call handler container for all expansions currently defined at execution
        time, including all static commands.

        Plugins wishing to programatically call expansions should use this.

        Raises:
            scrolls.interpreter.errors.InternalInterpreterError: If this property is not initialized.
        """
        if self._all_expansion_handlers is None:
            raise errors.InternalInterpreterError(
                self, "Bad context: _all_expansion_handlers not initialized."
            )

        return self._all_expansion_handlers

    def init_handlers(
            self,
            interpreter_command_handlers: 'callhandler.CallHandlerContainer[None]',
            interpreter_expansion_handlers: 'callhandler.CallHandlerContainer[str]'
    ) -> None:
        """
        Internal to the interpreter. This is called with the static command
        handler containers belonging to the interpreter when the context is
        initialized.
        """
        self._all_command_handlers = callhandler.ChoiceCallHandlerContainer(
            self.runtime_commands,
            interpreter_command_handlers
        )
        self._all_expansion_handlers = callhandler.ChoiceCallHandlerContainer(
            self.runtime_expansions,
            interpreter_expansion_handlers
        )

    @property
    def interpreter(self) -> 'run.Interpreter':
        """
        The interpreter running using this context.

        Raises:
            scrolls.interpreter.errors.InternalInterpreterError: If this property is not initialized.
        """
        if self._interpreter is None:
            raise errors.InternalInterpreterError(
                self, "Interpreter is not initialized."
            )

        return self._interpreter

    @interpreter.setter
    def interpreter(self, interpreter: 'run.Interpreter') -> None:
        self._interpreter = interpreter

    @property
    def current_node(self) -> ast.ASTNode:
        """
        The current `scrolls.ast.ASTNode` being interpreted.

        Raises:
            scrolls.interpreter.errors.InternalInterpreterError: If there is no current node.
        """
        if self._current_node is None:
            raise errors.InternalInterpreterError(
                self, "Current node is not initialized."
            )

        return self._current_node

    @current_node.setter
    def current_node(self, node: ast.ASTNode) -> None:
        self._current_node = node

    def _call_check(self) -> None:
        if self._call_context is None:
            raise errors.InternalInterpreterError(
                self, "Current context is not a call."
            )

    @property
    def call_stack(self) -> t.Sequence[struct.CallContext]:
        """
        The call stack. Used primarily for tracking return values in runtime calls, and feeding
        call information to `scrolls.interpreter.callhandler.CallHandler` implementations. Variables scopes are tracked separately.
        See `scrolls.interpreter.state.InterpreterContext.vars`.

        .. WARNING::
            This stack does not contain the current call. See `InterpreterContext.call_context` for that.
        """
        return self._call_stack

    @property
    def call_context(self) -> struct.CallContext:
        """
        The current call context.
        """
        self._call_check()
        return t.cast(struct.CallContext, self._call_context)

    @property
    def parent_call_context(self) -> struct.CallContext:
        """
        Get the context of the call that called the current one. Can be used to
        influence signals in the parent context.
        """
        self._call_check()
        if not self.call_stack:
            raise errors.InternalInterpreterError(
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
    def arg_nodes(self) -> struct.ArgSourceMap[ast.ASTNode]:
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
            scrolls.interpreter.errors.InternalInterpreterError: If the current context is not a call.
        """
        if self.call_context.control_node is None:
            raise errors.InternalInterpreterError(
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
        self._call_context = struct.CallContext(
            "__main__",
            [],
            struct.ArgSourceMap(),
            None
        )

    def set_call(
            self,
            command: str,
            args: t.Sequence[str],
            arg_nodes: struct.ArgSourceMap[ast.ASTNode],
            control_node: t.Optional[ast.ASTNode] = None
    ) -> None:
        """
        Sets the current call context, overwriting whatever was previously current. If you want to preserve the
        current context for later use, see `scrolls.interpreter.state.InterpreterContext.push_call`

        .. WARNING::
            Provided for advanced usage, this is usually done automatically. Typical users will never need to call this.
        """
        self._call_context = struct.CallContext(
            command,
            args,
            arg_nodes,
            control_node
        )

    def push_call(self) -> None:
        """
        Duplicate the current call context and push it onto the call stack. Should be followed up with
        `scrolls.interpreter.state.InterpreterContext.set_call` to create a new context.

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
            scrolls.interpreter.errors.InternalInterpreterError: If not calls have been pushed.
        """
        if not self._call_stack:
            raise errors.InternalInterpreterError(
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
            scrolls.interpreter.errors.InterpreterError: If outside a call context, no call stack, or no runtime call contexts found.
        """
        self._call_check()

        if not self.call_stack:
            raise errors.InterpreterError(
                self,
                f"cannot return, no call stack (outside calls)"
            )

        for ctx in reversed(self.call_stack):
            if ctx.runtime_call:
                ctx.return_value = retval
                return

        raise errors.InterpreterError(
            self,
            f"cannot return outside of function"
        )

    def get_backtrace(self) -> str:
        """
        Gets a printable string showing the full call backtrace for this
        context.
        """
        stack = list(self.call_stack) + [self.call_context]
        stack_size = len(stack)
        id_size = int(math.log(stack_size, 10)) + 1

        trace = [
            "backtrace (most recent call last)",
            struct.CallContext.trace_banner(id_size),
            *[call_ctx.trace_str(count, id_size) for count, call_ctx in enumerate(stack)]
        ]

        return "\n".join(trace)
