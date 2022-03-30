import random
import typing as t
from functools import reduce

from . import ast, interpreter

__all__ = (
    "StdIoCommandHandler",
    "BuiltinControlHandler",
    "BuiltinCommandHandler",
    "RandomExpansionHandler",
    "ArithmeticExpansionHandler",
    "ComparisonExpansionHandler",
    "LogicExpansionHandler",
    "StringExpansionHandler",
    "TRUE",
    "FALSE",
    "bool_to_scrolls_bool",
    "scrolls_bool_to_bool",
    "BuiltinInitializer"
)


TRUE = "1"
FALSE = "0"


def scrolls_bool_to_bool(x: str) -> bool:
    # "0" is interpreted as FALSE, everything else as TRUE.
    return not x == FALSE


def bool_to_scrolls_bool(b: bool) -> str:
    return TRUE if b else FALSE


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


class BuiltinInitializer(interpreter.Initializer):
    def handle_call(self, context: interpreter.InterpreterContext) -> None:
        context.set_var("true", TRUE)
        context.set_var("false", FALSE)
        context.runtime_commands.add(interpreter.RuntimeCallHandler(), "__def__")
        context.runtime_expansions.add(interpreter.RuntimeCallHandler(), "__def__")


class BuiltinCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements built-in command statements
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("set", self.set)
        self.add_call("unset", self.unset)
        self.add_call("stop", self.stop)
        self.add_call("return", self._return)

    def _return(self, context: interpreter.InterpreterContext) -> None:
        retval = " ".join(context.args)
        context.set_retval(retval)
        raise interpreter.InterpreterReturn()

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

    def stop(self, context: interpreter.InterpreterContext) -> None:
        raise interpreter.InterpreterStop


class BuiltinControlHandler(interpreter.CallbackControlHandler):
    """
    Implements built-in control statements
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("repeat", self.repeat)
        self.add_call("for", self._for)
        self.add_call("if", self._if)
        self.add_call("while", self._while)
        self.add_call("def", self._def)

    def _def(self, context: interpreter.InterpreterContext) -> None:
        args = context.args

        if len(args) < 1:
            raise InterruptedError(
                context,

            )

        command_calls = context.control_node.find_all(
            lambda node: (node.type == ast.ASTNodeType.COMMAND_CALL and
                          bool(node.children))
        )

        has_return = False
        for node in command_calls:
            name_node = node.children[0]

            if name_node.type == ast.ASTNodeType.STRING and name_node.str_content() == "return":
                has_return = True
                break

        if has_return:
            t.cast(
                interpreter.RuntimeCallHandler[str],
                context.runtime_expansions.get("__def__")
            ).define(args[0], context.control_node, args[1:])
        else:
            t.cast(
                interpreter.RuntimeCallHandler[None],
                context.runtime_commands.get("__def__")
            ).define(args[0], context.control_node, args[1:])

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

    def _if(self, context: interpreter.InterpreterContext) -> None:
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"if: needs one and only one argument"
            )

        if scrolls_bool_to_bool(context.args[0]):
            context.interpreter.interpret_statement(context, context.control_node)

    def _while(self, context: interpreter.InterpreterContext) -> None:
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"while: needs one and only one argument"
            )

        arg = context.args[0]

        while scrolls_bool_to_bool(arg):
            context.interpreter.interpret_statement(context, context.control_node)

            # HACK:
            # In order for while to work right, we need to re-evaluate the argument
            # every time.
            arg = context.interpreter.interpret_string_or_expansion(context, context.arg_nodes[0])[0]


class RandomExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements random expansions.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("select", self.select)
        self.add_call("shuffle", self.shuffle)
        self.add_call("uniform", self.uniform)

    def select(self, context: interpreter.InterpreterContext) -> str:
        """
        Randomly selects one of the arguments and returns it.
        """
        return random.choice(context.args)

    def shuffle(self, context: interpreter.InterpreterContext) -> str:
        """
        Shuffle the arguments given and return them.
        """
        args = list(context.args)
        random.shuffle(args)
        return " ".join(args)

    def uniform(self, context: interpreter.InterpreterContext) -> str:
        """
        Returns a random floating point number between two bounds, inclusive.
        """
        if len(context.args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"uniform: must have two args. (got {', '.join(context.args)})"
            )

        try:
            lower = float(context.args[0])
            upper = float(context.args[1])
        except ValueError as e:
            raise interpreter.InterpreterError(
                context,
                f"uniform: {str(e)}"
            )

        return str(random.uniform(lower, upper))


class ArithmeticExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic arithmetic expansions. These aren't very efficient, but
    if you want efficiency, you shouldn't be using an interpreted language
    with no JIT being interpreted by another interpreted language. :)
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("+", self.add)
        self.add_call("-", self.sub)
        self.add_call("*", self.mul)
        self.add_call("/", self.div)
        self.add_call("%", self.mod)

    @staticmethod
    def force_float(context: interpreter.InterpreterContext, x: str) -> float:
        try:
            return float(x)
        except ValueError as e:
            raise interpreter.InterpreterError(
                context,
                f"bad float value {x}"
            )

    @staticmethod
    def force_all_float(context: interpreter.InterpreterContext) -> t.Sequence[float]:
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                f"arithmetic expansion must take at least one argument"
            )

        return [
            ArithmeticExpansionHandler.force_float(context, x) for x in context.args
        ]

    @staticmethod
    def product(l: t.Sequence[float]) -> float:
        return reduce(lambda x, y: x * y, l, 1.0)

    def add(self, context: interpreter.InterpreterContext) -> str:
        return str(sum(self.force_all_float(context)))

    def sub(self, context: interpreter.InterpreterContext) -> str:
        args = self.force_all_float(context)

        if len(args) == 1:
            return str(-args[0])

        return str(args[0] - sum(args[1:]))

    def mul(self, context: interpreter.InterpreterContext) -> str:
        return str(self.product(self.force_all_float(context)))

    def div(self, context: interpreter.InterpreterContext) -> str:
        args = self.force_all_float(context)
        return str(args[0] / self.product(args[1:]))

    def mod(self, context: interpreter.InterpreterContext) -> str:
        args = self.force_all_float(context)
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"mod: must have exactly 2 args"
            )

        return str(int(args[0]) % int(args[1]))


class ComparisonExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic comparison operators.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("eq?", self.equals)
        self.add_alias("==", "eq?")
        self.add_call("neq?", self.not_equals)
        self.add_call(">", self.gt)
        self.add_call("<", self.lt)
        self.add_call(">=", self.gte)
        self.add_call("<=", self.lte)
        self.add_call("in?", self._in)

    def equals_bool(self, context: interpreter.InterpreterContext) -> bool:
        args = context.args
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name}: must have exactly 2 args"
            )

        try:
            float_args = ArithmeticExpansionHandler.force_all_float(context)
            return float_args[0] == float_args[1]
        except interpreter.InterpreterError:
            return args[0] == args[1]

    def get_numeric_compare_args(self, context: interpreter.InterpreterContext) -> t.Tuple[float, float]:
        args = context.args
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name}: must have exactly 2 args"
            )

        a, b = ArithmeticExpansionHandler.force_all_float(context)

        return a, b

    def equals(self, context: interpreter.InterpreterContext) -> str:
        return bool_to_scrolls_bool(self.equals_bool(context))

    def not_equals(self, context: interpreter.InterpreterContext) -> str:
        return bool_to_scrolls_bool(not self.equals_bool(context))

    def gt(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return bool_to_scrolls_bool(a > b)

    def lt(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return bool_to_scrolls_bool(a < b)

    def gte(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return bool_to_scrolls_bool(a >= b)

    def lte(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return bool_to_scrolls_bool(a <= b)

    def _in(self, context: interpreter.InterpreterContext) -> str:
        if len(context.args) == 0:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name} requires at least one argument"
            )

        return bool_to_scrolls_bool(context.args[0] in context.args[1:])


class LogicExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic logic operators.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("not", self._not)

    def _not(self, context: interpreter.InterpreterContext) -> str:
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"not: need one and only one argument"
            )

        return bool_to_scrolls_bool(not scrolls_bool_to_bool(context.args[0]))


class StringExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic string manipulation functions.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("cat", self.concat)
        self.add_alias("concat", "cat")

    def concat(self, context: interpreter.InterpreterContext) -> str:
        return "".join(context.args)
