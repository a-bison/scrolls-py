import random

from . import interpreter

__all__ = (
    "StdIoCommandHandler",
    "BuiltinControlHandler",
    "BuiltinCommandHandler",
    "RandomExpansionHandler"
)


class StdIoCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements input and output commands using stdout/stdin.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("print", self.print)
        self.add_call("input", self.input)

    def print(self, context: interpreter.InterpreterContext) -> None:
        print(" ".join(context.args))

    def input(self, context: interpreter.InterpreterContext) -> None:
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                "input: variable name is not specified"
            )

        result = input()
        context.set_var(context.args[0], result)


class BuiltinCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements built-in command statements
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("set", self.set)
        self.add_call("unset", self.unset)

    def set(self, context: interpreter.InterpreterContext) -> None:
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                "set: variable name is not specified"
            )

        context.set_var(context.args[0], " ".join(context.args[1:]))

    def unset(self, context: interpreter.InterpreterContext) -> None:
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                "unset: variable name is not specified"
            )

        try:
            context.del_var(context.args[0])
        except KeyError:
            raise interpreter.InterpreterError(
                context,
                f"unset: no such variable {context.args[0]}"
            )


class BuiltinControlHandler(interpreter.CallbackControlHandler):
    """
    Implements built-in control statements
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("repeat", self.repeat)
        self.add_call("for", self._for)

    def repeat(self, context: interpreter.InterpreterContext) -> None:
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                "repeat requires exactly one argument, the number of times to repeat"
            )

        context.current_node = context.arg_nodes[0]

        try:
            repeat_times = int(context.args[0])
        except ValueError:
            raise interpreter.InterpreterError(
                context,
                f"'{context.args[0]}' is not a valid integer"
            )

        control_node = context.control_node
        for _ in range(repeat_times):
            context.interpreter.interpret_statement(context, control_node)

    def _for(self, context: interpreter.InterpreterContext) -> None:
        if not context.args or len(context.args) < 3:
            raise interpreter.InterpreterError(
                context,
                "bad format in !for: expected !for(VARNAME in ARGS)"
            )

        var_name, _in, *items = context.args

        if _in != "in":
            context.current_node = context.arg_nodes[1]
            raise interpreter.InterpreterError(
                context,
                f"unexpected token '{_in}', should be 'in'"
            )

        control_node = context.control_node
        for item in items:
            context.set_var(var_name, item)
            context.interpreter.interpret_statement(context, control_node)

        context.del_var(var_name)


class RandomExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements random expansions.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("select", self.select)

    def select(self, context: interpreter.InterpreterContext) -> str:
        """
        Randomly selects one of the arguments and returns it.
        """
        return random.choice(context.args)
