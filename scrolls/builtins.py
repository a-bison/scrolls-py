"""
Built in Scrolls language features.

.. include:: pdoc/builtins.md
"""
import math
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
    "FileCommandHandler",
    "FileExpansionHandler",
    "base_config",
    "file_config",
    "unified_config"
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

file_config: containers.DecoratorInterpreterConfig = containers.DecoratorInterpreterConfig()
"""
A configuration object containing base Scrolls utilities for working with files.
Consists of:

- `FileExpansionHandler`
- `FileCommandHandler`
"""

unified_config: containers.DecoratorInterpreterConfig = containers.DecoratorInterpreterConfig()
"""
Adds `use-unified-commands`. After this command is called, all expansions may be called
as commands. Their return value will be discarded. Note that if a command exists with
the same name as an expansion, 

Consists of:


"""


class StdIoCommandHandler(interpreter.CallbackCommandHandler):
    """
    Implements input and output commands using stdout/stdin.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("print", self.print)
        self.add_call("write", self.write)
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

    def write(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `write` command. Prints all arguments passed to it, joined
        by spaces. The difference vs. `print` is that `print` appends a newline,
        while `write` does not.

        **Usage**
        ```scrolls
        write hello world foo bar
        ```
        """
        print(" ".join(context.args), end="")

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


@file_config.commandhandler
class FileCommandHandler(interpreter.CallbackCommandHandler):
    """
    Defines commands for working with files.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("file-close", self.close)

    def close(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements `file-close`. If you're looking for `file-open`, see
        `FileExpansionHandler.open`.

        **Usage**
        ```scrolls
        set f $(file-open file w)
        # do things to file...
        file-close $f
        ```
        """
        datatypes.require_arg_length(context, 1)
        fid, _ = datatypes.require_numeric(context, context.args[0])
        context.close_file(int(fid))


@file_config.expansionhandler
class FileExpansionHandler(interpreter.CallbackExpansionHandler):
    """
    Defines expansions for working with files.
    """
    def __init__(self) -> None:
        super().__init__()
        self.add_call("file-open", self.open)
        self.add_call("file-read", self.read)

    def open(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `file-open`. If you're looking for `file-close`, see
        `FileCommandHandler.close`.

        `file-open` returns an integer ID used as a handle to the file.
        This ID should be saved and used for all `file-*` functions.

        **Usage**
        ```scrolls
        set f $(file-open file w)
        # do things to file...
        file-close $f
        ```
        """
        datatypes.require_arg_length(context, 1)

        if len(context.args) > 1:
            mode = context.args[1]
        else:
            # default is read
            mode = "r"

        return str(context.open_file(context.args[0], mode))

    def read(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `file-read`. Reads an entire file and returns a string.

        **Usage**
        ```scrolls
        set f $(file-open file w)
        print $(file-read $f)
        file-close $f
        ```
        """
        datatypes.require_arg_length(context, 1)
        fid, _ = datatypes.require_numeric(context, context.args[0])

        f = context.get_file(int(fid))
        return f.read()


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
        self.add_call("elif", self.elif_)
        self.add_call("else", self.else_)
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

    def __cond_base(self, context: interpreter.InterpreterContext, respect_else_signal: bool) -> None:
        # Base conditional control call implementation
        if len(context.args) != 1:
            raise interpreter.InterpreterError(
                context,
                f"if: needs one and only one argument"
            )

        if respect_else_signal and not context.parent_call_context.else_signal:
            return

        check_result = datatypes.str_to_bool(context.args[0])

        if datatypes.str_to_bool(context.args[0]):
            context.interpreter.interpret_statement(context, context.control_node)

        # Signal to else-like control structures
        context.parent_call_context.else_signal = not check_result

    def if_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `if` control structure. Takes one argument, a boolean. If it's `scrolls.datatypes.TRUE`,
        executes the body statement. Otherwise, the body is skipped.
        [`elif`](#scrolls.builtins.BuiltinControlHandler.elif_) and
        [`else`](#scrolls.builtins.BuiltinControlHandler.else_) may
        be used to execute code if the condition is false.

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
        self.__cond_base(context, respect_else_signal=False)

    def elif_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `elif` control structure. Takes one argument, a boolean.  If it's `scrolls.datatypes.TRUE`,
        executes the body statement. Otherwise, the body is skipped and the next
        [`elif`](#scrolls.builtins.BuiltinControlHandler.elif_) or
        [`else`](#scrolls.builtins.BuiltinControlHandler.else_) is
        tried. Must be used after [`if`](#scrolls.builtins.BuiltinControlHandler.if_).

        **Usage**
        ```scrolls
        !if($false) {
            print "if: this will not print"
        } !elif($true) {
            print "elif: this will print"
        } !else {
            print "else: this will not print"
        }
        ```
        """
        self.__cond_base(context, respect_else_signal=True)

    def else_(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `else` control structure. Takes no arguments. Must be
        paired with a conditional to execute the body. See
        [`if`](#scrolls.builtins.BuiltinControlHandler.if_) and
        [`elif`](#scrolls.builtins.BuiltinControlHandler.elif_).

        **Usage**
        ```scrolls
        !if($false) {
            print "this will not print"
        } !else {
            print "this will print"
        }
        ```
        """
        if len(context.args) != 0:
            raise interpreter.InterpreterError(
                context,
                f"else: does not take arguments"
            )

        if context.parent_call_context.else_signal:
            context.interpreter.interpret_statement(context, context.control_node)

            # Once the else signal has been interpreted, "consume" it so it can't be
            # used again.
            context.parent_call_context.else_signal = False

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
        self.add_call("**", self.power)
        self.add_call("sqrt", self.sqrt)
        self.add_call("round", self.round)
        self.add_call("floor", self.floor)
        self.add_call("ceil", self.ceil)

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

    def power(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `**` (power). More than two arguments performs successive powers,
        for example `$(** 2 3 4)` is equivalent to `(2^3)^4`.

        **Usage**
        ```scrolls
        print $(** 2 3) # prints 8
        print $(** 2 3 4) # prints 4096
        print $(** 2.1 3) # prints
        ```
        """
        return self.__reduce(context, operator.pow)

    def sqrt(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `sqrt` (square root). Takes one argument. Always returns a float,
        so convert to int (see `ArithmeticExpansionHandler.toint`) if needed.

        **Usage**
        ```scrolls
        print $(sqrt 16) # prints 4.0
        ```
        """
        return self.__unary(context, math.sqrt)

    def round(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `round`. Takes one or two arguments.

        If one argument, will round to the nearest whole number and
        return an integer. Otherwise, rounds to the nearest decimal place
        specified by the second argument and returns a float.

        **Usage**
        ```scrolls
        print $(round 4.7281) # prints 5
        print $(round 4.7281, 0) # prints 5.0
        print $(round 4.7281, 2) # prints 4.73
        # etc...
        ```
        """
        # Datatype stuff is done manually here because it's not quite like the
        # normal arithmetic operations.
        datatypes.require_arg_length(context, 1)

        if len(context.args) == 1:
            return str(round(float(context.args[0])))

        return str(round(float(context.args[0]), int(context.args[1])))

    def floor(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `floor`. Takes one argument. Returns the greatest integer less
        than or equal to the argument.

        **Usage**
        ```scrolls
        print $(floor 4.6) # prints 4
        print $(floor -4.6) # prints -5
        ```
        """
        return self.__unary(context, math.floor)

    def ceil(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `ceil`. Takes one argument. Returns the lowest integer greater
        than or equal to the argument.

        **Usage**
        ```scrolls
        print $(ceil 4.6) # prints 5
        print $(ceil -4.6) #prints -4
        ```
        """
        return self.__unary(context, math.ceil)


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
        self.add_call("===", self.str_equals)
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

    def str_equals(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `===`. Takes only two arguments.

        `===` is the strong comparison operator. It only operates on strings,
        and no implicit conversion is done.

        Contrast with the behavior of `ComparisonExpansionHandler.equals`.

        **Usage**
        ```scrolls
        print $(=== 0123 123) # prints 0
        print $(=== hello hello) # prints 0
        ```
        """
        args = context.args
        if len(args) != 2:
            raise interpreter.InterpreterError(
                context,
                f"{context.call_name}: must have exactly 2 args"
            )

        return datatypes.bool_to_str(args[0] == args[1])

    def equals(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `==`, or `eq?`. Takes only two arguments.

        `==` is a weak comparison operator. If both arguments can be interpreted numerically, they will be converted
        to numbers before testing for equivalence. Otherwise, `==` just tests if the strings passed are equal.

        Contrast with the behavior of `ComparisonExpansionHandler.str_equals`.

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
        self.add_call("getc", self.getc)
        self.add_call("len", self.len)
        self.add_call("ord", self.ord)
        self.add_call("chr", self.chr)
        self.add_call("vempty?", self.vempty)
        self.add_call("vhead", self.vhead)
        self.add_call("vtail", self.vtail)
        self.add_call("vlen", self.vlen)
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

    def getc(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `getc`. Gets a single character from a string, starting at 0.

        **Usage**
        ```scrolls
        set example "Hello"
        print $(getc $example 4) # prints 'o'
        ```
        """
        datatypes.require_arg_length(context, 2)
        n = int(datatypes.require_numeric(context, context.args[1])[0])

        return context.args[0][n]

    def len(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `len`. Gets the length of the passed string.

        **Usage**
        ```scrolls
        print $(len "hello") # prints 5
        ```
        """
        datatypes.require_arg_length(context, 1)
        return str(len(context.args[0]))

    def ord(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `ord`. Converts a single character to its integer equivalent.

        **Usage**
        ```scrolls
        print $(ord "h") # prints 104
        ```
        """
        datatypes.require_arg_length(context, 1)
        return str(ord(context.args[0]))

    def chr(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `chr`. Converts a number into the character it corresponds to.

        **Usage**
        ```scrolls
        print $(chr 104) # prints h
        ```
        """
        datatypes.require_arg_length(context, 1)
        c = int(datatypes.require_numeric(context, context.args[0])[0])
        return chr(c)

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

    def vlen(self, context: interpreter.InterpreterContext) -> str:
        """
        Implements `vlen`. Returns the number of elements in a vector.

        **Usage**
        ```scrolls
        set vec "a b c d"
        print $(vlen $vec) # prints 4.
        ```
        """
        datatypes.require_arg_length(context, 1)
        return str(len(context.args[0].split()))

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


@unified_config.commandhandler
class UnifiedCommandSettingHandler(interpreter.CallbackCommandHandler):
    def __init__(self) -> None:
        super().__init__()
        self.add_call("use-unified-commands", self.use_unified_commands)

        self.enable_unified_commands = False
        self.expansion_handler: t.Optional[interpreter.CallHandlerContainer[str]] = None

    def use_unified_commands(self, context: interpreter.InterpreterContext) -> None:
        """
        Implements the `use-unified-commands` command. When used, unified commands
        will be enabled for the rest of the script, allowing all expansions
        to be used as commands. The most common way this would be used is if
        you have expansions with side-effects, and don't care about the return
        value.

        **Usage**
        ```scrolls
        use-unified-commands

        set some-global-variable "before"

        !def(test) {
            set some-global-variable "after"
            return "blah"
        }

        print $some-global-variable
        test # test may be used as command here despite being defined as an expansion
        print $some-global-variable
        ```
        """
        self.enable_unified_commands = True

        # workaround: need to store reference to the context to access
        # expansion handlers in __contains__ override. For now this is OK,
        # since it's not expected that the context will change mid-script.

        # FIXME: Construct this once in the context object.
        # It's constructed on the fly on *every call*... not great, and doesn't
        # let extensions access the whole thing.
        self.expansion_handler = interpreter.ChoiceCallHandlerContainer(
            context.runtime_expansions,
            context.interpreter.expansion_handlers
        )

    # override
    def __contains__(self, command_name: str) -> bool:
        super_contains = super().__contains__(command_name)

        if super_contains:
            return True
        elif self.enable_unified_commands:
            try:
                self.expansion_handler.get_for_call(command_name)
                return True
            except KeyError:
                return False
        else:
            return False

    # override
    def handle_call(self, context: interpreter.InterpreterContext) -> None:
        # If no unified commands, defer to super.
        if not self.enable_unified_commands:
            super().handle_call(context)
            return

        # For unified, proceed normally if superclass contains the call.
        # Otherwise, call an expansion and discard the return value.
        if super().__contains__(context.call_name):
            super().handle_call(context)
        else:
            self.expansion_handler.get_for_call(context.call_name).handle_call(context)
