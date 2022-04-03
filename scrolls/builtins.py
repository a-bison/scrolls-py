import functools
import operator
import random
import typing as t

from . import ast, containers, datatypes, interpreter

__all__ = (
    "StdIoCommandHandler",
    "BuiltinControlHandler",
    "BuiltinCommandHandler",
    "RandomExpansionHandler",
    "ArithmeticExpansionHandler",
    "ComparisonExpansionHandler",
    "LogicExpansionHandler",
    "StringExpansionHandler",
    "BuiltinInitializer",
    "base_config"
)

base_config = containers.DecoratorInterpreterConfig()


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


@base_config.initializer
class BuiltinInitializer(interpreter.Initializer):
    def handle_call(self, context: interpreter.InterpreterContext) -> None:
        context.set_var("true", datatypes.TRUE)
        context.set_var("false", datatypes.FALSE)
        context.runtime_commands.add(interpreter.RuntimeCallHandler(), "__def__")
        context.runtime_expansions.add(interpreter.RuntimeCallHandler(), "__def__")


@base_config.commandhandler
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


@base_config.controlhandler
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

        if datatypes.str_to_bool(context.args[0]):
            context.interpreter.interpret_statement(context, context.control_node)

    def _while(self, context: interpreter.InterpreterContext) -> None:
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"while: needs one and only one argument"
            )

        arg = context.args[0]

        while datatypes.str_to_bool(arg):
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


@base_config.expansionhandler
class ArithmeticExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic arithmetic expansions. These aren't very efficient, but
    if you want efficiency, you shouldn't be using an interpreted language
    with no JIT being interpreted by another interpreted language. :)
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("toint", self.toint)
        self.add_call("tofloat", self.tofloat)
        self.add_call("+", self.add)
        self.add_call("-", self.sub)
        self.add_call("*", self.mul)
        self.add_call("/", self.div)
        self.add_call("//", self.intdiv)
        self.add_call("%", self.mod)

    @staticmethod
    def unary(context: interpreter.InterpreterContext, op: datatypes.UnaryNumOpT) -> str:
        return str(datatypes.apply_unary_num_op(context, op)[0])

    @staticmethod
    def binary(context: interpreter.InterpreterContext, op: datatypes.BinaryNumOpT) -> str:
        return str(datatypes.apply_binary_num_op(context, op)[0])

    @staticmethod
    def mass(
        context: interpreter.InterpreterContext,
        reduce_op: datatypes.BinaryNumOpT,
        final_op: datatypes.BinaryNumOpT
    ) -> str:
        return str(datatypes.apply_mass_binary_num_op(context, reduce_op, final_op)[0])

    @staticmethod
    def reduce(
        context: interpreter.InterpreterContext,
        reduce_op: datatypes.BinaryNumOpT
    ) -> str:
        return str(datatypes.apply_reduce_binary_num_op(context, reduce_op)[0])

    def sub(self, context: interpreter.InterpreterContext) -> str:
        # Sub behaves a little differently. If only one arg, negate instead of subtracting.
        if len(context.args) == 1:
            return self.unary(context, operator.neg)

        return self.mass(context, reduce_op=operator.add, final_op=operator.sub)

    def toint(self, context: interpreter.InterpreterContext) -> str: return self.unary(context, datatypes.toint)
    def tofloat(self, context: interpreter.InterpreterContext) -> str: return self.unary(context, datatypes.tofloat)
    def add(self, context: interpreter.InterpreterContext) -> str: return self.reduce(context, operator.add)
    def mul(self, context: interpreter.InterpreterContext) -> str: return self.reduce(context, operator.mul)
    def div(self, context: interpreter.InterpreterContext) -> str: return self.mass(context, reduce_op=operator.mul, final_op=operator.truediv)
    def intdiv(self, context: interpreter.InterpreterContext) -> str: return self.mass(context, reduce_op=operator.mul, final_op=operator.floordiv)
    def mod(self, context: interpreter.InterpreterContext) -> str: return self.binary(context, operator.mod)


@base_config.expansionhandler
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
            float_args, _ = datatypes.require_all_numeric(context, args)
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

        (a, b), _ = datatypes.require_all_numeric(context, args)

        return a, b

    def equals(self, context: interpreter.InterpreterContext) -> str:
        return datatypes.bool_to_str(self.equals_bool(context))

    def not_equals(self, context: interpreter.InterpreterContext) -> str:
        return datatypes.bool_to_str(not self.equals_bool(context))

    def gt(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return datatypes.bool_to_str(a > b)

    def lt(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return datatypes.bool_to_str(a < b)

    def gte(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return datatypes.bool_to_str(a >= b)

    def lte(self, context: interpreter.InterpreterContext) -> str:
        a, b = self.get_numeric_compare_args(context)
        return datatypes.bool_to_str(a <= b)

    def _in(self, context: interpreter.InterpreterContext) -> str:
        if len(context.args) == 0:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name} requires at least one argument"
            )

        return datatypes.bool_to_str(context.args[0] in context.args[1:])


@base_config.expansionhandler
class LogicExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic logic operators.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("not", self._not)
        self.add_call("and", self._and)
        self.add_call("or", self._or)
        self.add_call("xor", self._xor)

    @staticmethod
    def unary(context: interpreter.InterpreterContext, op: datatypes.UnaryNumOpT) -> str:
        return datatypes.bool_to_str(datatypes.apply_unary_bool_op(context, op))

    @staticmethod
    def reduce(context: interpreter.InterpreterContext, op: datatypes.BinaryNumOpT) -> str:
        return datatypes.bool_to_str(datatypes.apply_reduce_bool_op(context, op))

    def _not(self, context: interpreter.InterpreterContext) -> str: return self.unary(context, operator.not_)
    def _and(self, context: interpreter.InterpreterContext) -> str: return self.reduce(context, operator.and_)
    def _or(self, context: interpreter.InterpreterContext) -> str: return self.reduce(context, operator.or_)
    def _xor(self, context: interpreter.InterpreterContext) -> str: return self.reduce(context, operator.xor)


@base_config.expansionhandler
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
