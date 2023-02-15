"""
Interpreter-specific errors.
"""
from .. import errors
from . import state

__all__ = (
    "InterpreterError",
    "InternalInterpreterError",
    "InterpreterReturn",
    "InterpreterStop",
    "MissingCallError",
)


class InterpreterError(errors.PositionalError):
    """
    A generic interpreter error. All interpreter errors should subclass this.
    """
    def __init__(self, ctx: state.InterpreterContext, message: str):
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
        trace = self.ctx.get_backtrace()
        s = [trace]

        if self.ctx.current_node.has_token():
            s += [
                "",
                "where:",
                super().__str__()
            ]
        else:
            s.append("Interpreter error on node with uninitialized token.")

        return "\n".join(s)


class MissingCallError(InterpreterError):
    """
    Raised when a call cannot be found.
    """
    def __init__(self, ctx: state.InterpreterContext, call_type: str, call_name: str):
        self.call = call_name
        message = f"{call_type.capitalize()} '{call_name}' not found."
        super().__init__(
            ctx, message
        )


class InternalInterpreterError(InterpreterError):
    """
    Raised on critical interpreter errors that are usually the result of bugs.
    """
    def __init__(self, context: state.InterpreterContext, message: str):
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
