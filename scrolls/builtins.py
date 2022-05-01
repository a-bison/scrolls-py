"""
Built in Scrolls language features.

.. include:: pdoc/builtins.md
"""

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

base_config: containers.DecoratorInterpreterConfig = containers.DecoratorInterpreterConfig()
"""
A configuration object containing the Scrolls base language. This currently consists of:

- `BuiltinControlHandler`
- `BuiltinCommandHandler`
- `BuiltinInitializer`
- `ArithmeticExpansionHandler`
- `ComparisonExpansionHandler`
- `LogicExpansionHandler`
- `StringExpansionHandler`

.. WARNING::
    `print` and `input` are **not** defined as part of the base language, and must be added manually. See
    `StdIoCommandHandler`.
"""


class StdIoCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements input and output commands using stdout/stdin.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("print", self.print)
        self.add_call("input", self.input)

    def print(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `print` command. Prints all arguments passed to it, joined by spaces.

        **Usage**
        ```scrolls
        print hello world foo bar
        ```
        """
        print(" ".join(context.args))

    def input(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `input` command. Reads `stdin` for input, and stores the input in a variable named
        by the first argument.

        **Usage**
        ```scrolls
        input foo
        print $foo # prints what you entered
        ```
        """
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                "input: variable name is not specified"
            )

        result = input()
        context.set_var(context.args[0], result)


@base_config.initializer
class BuiltinInitializer(interpreter.Initializer):
    """
    Sets built in constants, and initializes plumbing used by
    [`def`](#scrolls.builtins.BuiltinControlHandler.def_) and
    [`return`](#scrolls.builtins.BuiltinCommandHandler.return_).

    ### Variables
    - `$true` - A true boolean.
    - `$false` - A false boolean.
    """
    def handle_call(self, context: interpreter.InterpreterContext) -> None:
        context.set_var("true", datatypes.TRUE)
        context.set_var("false", datatypes.FALSE)
        context.runtime_commands.add(interpreter.RuntimeCallHandler(), "__def__")
        context.runtime_expansions.add(interpreter.RuntimeCallHandler(), "__def__")


@base_config.commandhandler
class BuiltinCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements built-in command statements. In order for
    [`return`](#scrolls.builtins.BuiltinCommandHandler.return_)
    to be functional, `BuiltinControlHandler` and `BuiltinInitializer` must also be loaded.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("set", self.set)
        self.add_call("unset", self.unset)
        self.add_call("stop", self.stop)
        self.add_call("return", self.return_)
        self.add_call("nonlocal", self.nonlocal_)
        self.add_call("global", self.global_)

    def return_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `return` command. Returns all arguments passed to it as a single string, joined by spaces.
        If this command is present in a [`def`](#scrolls.builtins.BuiltinControlHandler.def_) block, that `def` block
        will define a new expansion call. Otherwise, it defines a command.

        Using this command outside a `def` block will result in an error.

        **Usage**
        ```scrolls
        !def(example foo) {
            return $foo
        }
        print $(example "hello world")
        ```
        """
        retval = " ".join(context.args)
        context.set_retval(retval)
        raise interpreter.InterpreterReturn()

    def set(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `set` command. Sets a variable. The first argument is the name of the variable. The rest of the
        arguments are joined by spaces and stored in the named variable.

        **Usage**
        ```scrolls
        set varname arg1 arg2 arg3
        print $varname # prints arg1 arg2 arg3
        ```
        """
        if not context.args:
            raise interpreter.InterpreterError(
                context,
                "set: variable name is not specified"
            )

        context.set_var(context.args[0], " ".join(context.args[1:]))

    def unset(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `unset` command. Deletes a variable. The first argument is the name of the variable to delete.

        **Usage**
        ```scrolls
        set varname hello
        print $varname # prints hello
        unset varname
        print $varname # ERROR
        ```
        """
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

    def nonlocal_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `nonlocal` command. Declares a variable as nonlocal, which allows variable references to modify
        variables in the enclosing scope.

        **Usage**
        ```scrolls
        !def(zero varname) {
            nonlocal $varname
            set $varname 0
        }
        !def(main) {
            set example 42
            zero example

            # "0" is printed, since example was declared nonlocal
            # in the zero function.
            print $example
        }

        set example 200
        main # prints "0"

        # Prints "200", since the zero call in main only
        # modifies the DIRECTLY enclosing scope.
        print $example
        ```
        """
        datatypes.require_arg_length(context, 1)
        context.vars.declare_nonlocal(context.args[0])

    def global_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `global` command. Declares a variable as global, which allows variable references to modify
        variables in the global scope.

        **Usage**
        ```scrolls
        !def(set_global varname *args) {
            global $varname
            set $varname $args
        }
        !def(main) {
            set_global example arg1 arg2 arg3
        }

        main

        # prints "arg1 arg2 arg3", since main->set_global example
        # sets a variable in the global scope.
        print $example
        ```
        """
        datatypes.require_arg_length(context, 1)
        context.vars.declare_global(context.args[0])

    def stop(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `stop` command. Stops the script execution. Takes no arguments.
        """
        raise interpreter.InterpreterStop()


@base_config.controlhandler
class BuiltinControlHandler(interpreter.CallbackControlHandler):
    """
    Implements built-in command statements. In order for
    [`def`](#scrolls.builtins.BuiltinControlHandler.def_)
    to be functional, `BuiltinCommandHandler` and `BuiltinInitializer` must also be loaded.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("repeat", self.repeat)
        self.add_call("for", self.for_)
        self.add_call("if", self.if_)
        self.add_call("while", self.while_)
        self.add_call("def", self.def_)

    def def_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `def` control structure. Allows the definition of new commands and expansion calls.
        The first argument is the name of the call to define. The rest of the arguments name the parameters to the
        call. The last parameter name may be prefixed with `*` to support variable arguments.

        **Usage**
        ```scrolls
        !def(example a b) {
            print "a is" $a
            print "b is" $b
        }

        # prints
        # a is foo
        # b is bar
        example foo bar

        !def(varargs_example x *args) {
            print "x is" $x
            print "the rest of the args are:"
            !for(i in $^args) print $i
        }

        # prints
        # x is 10
        # the rest of the args are:
        # foo
        # bar
        # baz
        varargs_example 10 foo bar baz
        ```
        """
        args = context.args
        datatypes.require_arg_length(context, 1)

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
        """
        Implements the `repeat` control structure. Takes a single integer argument, that repeats the body n times.

        **Usage**
        ```scrolls
        # prints "hello world" 4 times
        !repeat(4) {
            print "hello world"
        }
        ```
        """
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

    def for_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `for` control structure. The syntax is as follows: `!for(VARNAME in VECTOR) ...`

        **Usage**
        ```scrolls
        # prints
        # 1
        # 2
        # 3
        # 4
        # 5
        !for(x in 1 2 3 4 5) {
            print $x
        }
        ```
        """
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

    def if_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `if` control structure. Takes one argument, a boolean. If it's `scrolls.datatypes.TRUE`,
        executes the body statement. Otherwise, the body is skipped. `else` is not supported.

        **Usage**
        ```scrolls
        !if($true) {
            print "this will print"
        }
        !if($false) {
            print "this will not print"
        }
        ```
        """
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"if: needs one and only one argument"
            )

        if datatypes.str_to_bool(context.args[0]):
            context.interpreter.interpret_statement(context, context.control_node)

    def while_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `while` control structure. Takes one argument, a boolean. Repeats the body while
        the condition is `scrolls.datatypes.TRUE`.

        **Usage**
        ```scrolls
        # counting down from 10 to 1
        set i 10
        !while($(> 0 $i)) {
            print $i
            set i $(- $i 1)
        }
        ```
        """
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
        Implements the `select` expansion. Randomly selects one of the arguments and returns it.

        **Usage**
        ```scrolls
        # randomly prints either foo, bar, or baz
        print $(select foo bar baz)
        ```
        """
        return random.choice(context.args)

    def shuffle(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `shuffle` expansion. Shuffle the arguments given and return them.

        **Usage**
        ```scrolls
        print $(shuffle 1 2 3 4 5)
        ```
        """
        args = list(context.args)
        random.shuffle(args)
        return " ".join(args)

    def uniform(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `uniform` expansion. Returns a random floating point number between two bounds, inclusive.

        **Usage**
        ```scrolls
        print $(uniform 0 2) # print a random float between 0 and 2.
        ```
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
    with no JIT being interpreted by another interpreted language `:)`.

    Most of these are self-explanatory. Examples will be provided where appropriate.
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
    def __unary(context: interpreter.InterpreterContext, op: datatypes.UnaryNumOpT) -> str:
        return str(datatypes.apply_unary_num_op(context, op)[0])

    @staticmethod
    def __binary(context: interpreter.InterpreterContext, op: datatypes.BinaryNumOpT) -> str:
        return str(datatypes.apply_binary_num_op(context, op)[0])

    @staticmethod
    def __mass(
        context: interpreter.InterpreterContext,
        reduce_op: datatypes.BinaryNumOpT,
        final_op: datatypes.BinaryNumOpT
    ) -> str:
        return str(datatypes.apply_mass_binary_num_op(context, reduce_op, final_op)[0])

    @staticmethod
    def __reduce(
        context: interpreter.InterpreterContext,
        reduce_op: datatypes.BinaryNumOpT
    ) -> str:
        return str(datatypes.apply_reduce_binary_num_op(context, reduce_op)[0])

    def sub(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `-`.

        **Usage**
        ```scrolls
        print $(- 4) # negate a number
        print $(- 10 3) # subtract 3 from 10
        print $(- 10 1 2 3) # subtract 1, 2, and 3 from 10.
        ```
        """
        # Sub behaves a little differently. If only one arg, negate instead of subtracting.
        if len(context.args) == 1:
            return self.__unary(context, operator.neg)

        return self.__mass(context, reduce_op=operator.add, final_op=operator.sub)

    def toint(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `toint`. Forces a number to be an integer. If the input is a float, the decimal point
        will be truncated.
        """
        return self.__unary(context, datatypes.toint)

    def tofloat(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `tofloat`. Forces a number to be a float.
        """
        return self.__unary(context, datatypes.tofloat)

    def add(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `+`. `+` will take 2 or more arguments, and sum them all together.

        **Usage**
        ```scrolls
        print $(+ 2 3)
        print $(+ 1 10 34)
        ```
        """
        return self.__reduce(context, operator.add)

    def mul(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `*`. `*` will take 2 or more arguments, and multiplies them all together.

        **Usage**
        ```scrolls
        print $(* 2 3)
        print $(* 1 10 34)
        ```
        """
        return self.__reduce(context, operator.mul)

    def div(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `/`.

        **Usage**
        ```scrolls
        print $(/ 6 2) # prints 3.0
        print $(/ 20 2 5) # divides 20 by 2, then by 5. prints 2.0
        ```
        """
        return self.__mass(context, reduce_op=operator.mul, final_op=operator.truediv)

    def intdiv(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `//` (integer division).

        **Usage**
        ```scrolls
        print $(// 5 2) # prints 2.
        print $(// 20 2 3) # divides 20 by 2*3 (6), (3.3333...), then truncates float part. prints 3.
        ```
        """
        return self.__mass(context, reduce_op=operator.mul, final_op=operator.floordiv)

    def mod(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `%` (modulo). Takes only two arguments.

        **Usage**
        ```scrolls
        print $(% 5 2) # prints 1.
        ```
        """
        return self.__binary(context, operator.mod)


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

    def __equals_bool(self, context: interpreter.InterpreterContext) -> bool:
        args = context.args
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name}: must have exactly 2 args"
            )

        try:
            num_args, _ = datatypes.require_all_numeric(context, args)
            return num_args[0] == num_args[1]
        except interpreter.InterpreterError:
            return args[0] == args[1]

    def __get_numeric_compare_args(self, context: interpreter.InterpreterContext) -> t.Tuple[float, float]:
        args = context.args
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name}: must have exactly 2 args"
            )

        (a, b), _ = datatypes.require_all_numeric(context, args)

        return a, b

    def equals(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `==`, or `eq?`. Takes only two arguments.

        `==` is a weak comparison operator. If both arguments can be interpreted numerically, they will be converted
        to numbers before testing for equivalence. Otherwise, `==` just tests if the strings passed are equal.

        **Usage**
        ```scrolls
        print $(eq? 0123 123) # prints 1, numeric comparison
        print $(eq? hello hello) # prints 1, string comparison
        ```
        """
        return datatypes.bool_to_str(self.__equals_bool(context))

    def not_equals(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `ne?`. Note this is not aliased to `!=` due to `!` being a reserved character. Takes only two arguments.

        Same as with `ComparisonExpansionHandler.equals`, this operator implicitly converts to numbers when possible.

        **Usage**
        ```scrolls
        print $(ne? 0123 123) # prints 0, numeric comparison
        print $(ne? hello world) # prints 1, string comparison
        ```
        """
        return datatypes.bool_to_str(not self.__equals_bool(context))

    def gt(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `>`. Takes only two arguments, both must be numeric.

        **Usage**
        ```scrolls
        print $(> 0 3) # prints 1.
        ```
        """
        a, b = self.__get_numeric_compare_args(context)
        return datatypes.bool_to_str(a > b)

    def lt(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `<`. Takes only two arguments, both must be numeric.

        **Usage**
        ```scrolls
        print $(< 4 10) # prints 1.
        ```
        """
        a, b = self.__get_numeric_compare_args(context)
        return datatypes.bool_to_str(a < b)

    def gte(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `>=`. Takes only two arguments, both must be numeric.

        **Usage**
        ```scrolls
        print $(>= 10 4) # prints 1.
        print $(>= 4 4) # prints 1.
        ```
        """
        a, b = self.__get_numeric_compare_args(context)
        return datatypes.bool_to_str(a >= b)

    def lte(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `<=`. Takes only two arguments, both must be numeric.

        **Usage**
        ```scrolls
        print $(<= 4 10) # prints 1.
        print $(<= 4 4) # prints 1.
        ```
        """
        a, b = self.__get_numeric_compare_args(context)
        return datatypes.bool_to_str(a <= b)

    def _in(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `in?`. Takes at least one argument.

        **Usage**
        ```scrolls
        # in? x args...
        # Tests if x is in the following arguments.
        print $(in? blah) # always returns '0'.
        print $(in? bar foo bar baz) # returns '1'.
        ```
        """
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

    Related:
        `scrolls.datatypes.TRUE`
        `scrolls.datatypes.FALSE`
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("not", self.not_)
        self.add_call("and", self.and_)
        self.add_call("or", self.or_)
        self.add_call("xor", self.xor_)

    @staticmethod
    def __unary(context: interpreter.InterpreterContext, op: datatypes.UnaryNumOpT) -> str:
        return datatypes.bool_to_str(datatypes.apply_unary_bool_op(context, op))

    @staticmethod
    def __reduce(context: interpreter.InterpreterContext, op: datatypes.BinaryNumOpT) -> str:
        return datatypes.bool_to_str(datatypes.apply_reduce_bool_op(context, op))

    def not_(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `not` operator.

        **Usage**
        ```scrolls
        print $(not $true) # prints 0.
        ```
        """
        return self.__unary(context, operator.not_)

    def and_(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `and` operator. Takes 2 or more arguments, and `and`s them all together.

        **Usage**
        ```scrolls
        print $(and $true $false $true) # prints 0.
        print $(and $true $true) # prints 1.
        ```
        """
        return self.__reduce(context, operator.and_)

    def or_(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `or` operator. Takes 2 or more arguments, and `or`s them all together.

        **Usage**
        ```scrolls
        print $(or $true $false $true) # prints 1.
        print $(or $false $false) # prints 0.
        ```
        """
        return self.__reduce(context, operator.or_)

    def xor_(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements the `xor` operator. Takes 2 or more arguments. With 2 arguments, `xor` performs a standard XOR
        operation. With more arguments, `xor` will perform a parity check. It will return `scrolls.datatypes.TRUE`
        for an odd number of `scrolls.datatypes.TRUE` inputs, and `scrolls.datatypes.FALSE` for an even number of
        `scrolls.datatypes.TRUE` inputs.

        **Usage**
        ```scrolls
        print $(xor $true $false) # prints 1.
        print $(xor $true $false $true) # prints 0.
        ```
        """
        return self.__reduce(context, operator.xor)


@base_config.expansionhandler
class StringExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Implements basic string manipulation expansions.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("cat", self.concat)
        self.add_alias("concat", "cat")
        self.add_call("vempty?", self.vempty)
        self.add_call("vhead", self.vhead)
        self.add_call("vtail", self.vtail)
        self.add_call("rangev", self.rangev)

    def concat(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `cat`. Concatenates all arguments into one string and returns it. Commonly used to concatenate
        punctuation onto variable output.

        **Usage**
        ```scrolls
        set example "Hello world"
        print $(cat $example "!") # prints Hello World!
        ```
        """
        return "".join(context.args)

    def vempty(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `vempty?`. Returns `scrolls.datatypes.TRUE` if the passed vector is empty.

        **Usage**
        ```scrolls
        set empty_vec ""
        print $(vempty? $empty_vec) # prints 1.
        ```
        """
        datatypes.require_arg_length(context, 1)
        return datatypes.bool_to_str(not bool(context.args[0]))

    def vhead(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `vhead`. Returns the first element of a vector (the leftmost element).

        **Usage**
        ```scrolls
        set vec "2 4 8 16"
        print $(vhead $vec) # prints 2.
        ```
        """
        datatypes.require_arg_length(context, 1)
        return context.args[0].split(maxsplit=1)[0]

    def vtail(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `vtail`. Returns every element of a vector except the first.

        **Usage**
        ```scrolls
        set vec "2 4 8 16"
        print $(vtail $vec) # prints 4 8 16.
        ```
        """
        datatypes.require_arg_length(context, 1)
        return "".join(context.args[0].split(maxsplit=1)[1:])

    def rangev(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `rangev`. Returns a vector consisting of a range of numbers.

        **Usage**
        ```scrolls
        set min 0
        set max 4
        print $(rangev $min $max) # prints 0 1 2 3
        ```
        """
        datatypes.require_arg_length(context, 2)
        (a, b, *rest), _ = datatypes.require_all_numeric(context, context.args)

        a = int(a)
        b = int(b)

        return " ".join([str(x) for x in range(a, b)])
