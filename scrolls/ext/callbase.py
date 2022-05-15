"""
A basic call framework for Scrolls.

Takes care of the basic boilerplate for parsing options, and offers a slightly nicer decorator-based approach to
defining new Scrolls calls.

.. include:: ./pdoc/callbase.md
"""
import abc
import dataclasses
import enum
import logging
import numbers
import typing as t

import scrolls

__all__ = (
    "rangelimit",
    "make_callbase",
    "set_help",
    "OptionError",
    "OptionChoiceError",
    "OptionRangeLimitError",
    "OptionConversionError",
    "OptionRequiredMissingError",
    "Option",
    "OptionModifier",
    "CallBase",
    "CallbackCallBase",
    "CallBaseCallHandler"
)


logger = logging.getLogger(__name__)

OptionTV = t.TypeVar("OptionTV", str, int, float, bool)
T = t.TypeVar("T")
T_co = t.TypeVar("T_co", covariant=True)

CallBaseCallbackReturnTV = t.TypeVar("CallBaseCallbackReturnTV")
CallBaseCallbackT = t.Callable[[scrolls.InterpreterContext, t.Sequence[t.Any]], CallBaseCallbackReturnTV]


def rangelimit(
    node: scrolls.ASTNode,
    low: t.Optional[numbers.Real],
    val: numbers.Real,
    high: t.Optional[numbers.Real]
) -> None:
    """
    Check if val is between low and high. If not, raise a RangeLimitError.
    """

    if low is None and high is None:
        raise ValueError("low and high cannot both be None")

    if not (__rangecheck_lower(low, val) and __rangecheck_upper(high, val)):
        raise OptionRangeLimitError(node, low, val, high)


def __rangecheck_lower(
    low: t.Optional[numbers.Real],
    val: numbers.Real
) -> bool:
    if low is None:
        return True

    return low <= val


def __rangecheck_upper(
    high: t.Optional[numbers.Real],
    val: numbers.Real
) -> bool:
    if high is None:
        return True

    return val <= high


class OptionError(Exception):
    """
    Base class for errors parsing arguments.

    Args:
        node: The `scrolls.ast.ASTNode` corresponding to the argument that failed to parse.
    """
    def __init__(self, node: scrolls.ASTNode):
        self.node = node


class OptionRangeLimitError(OptionError):
    """
    Raised when a numeric argument (int, float) is outside the bounds set
    by the `Option`.
    """
    def __init__(
        self,
        node: scrolls.ASTNode,
        low: t.Optional[numbers.Real],
        val: numbers.Real,
        high: t.Optional[numbers.Real]
    ):
        super().__init__(node)
        self.low = low
        self.val = val
        self.high = high

    def __str__(self) -> str:
        if self.high is None:
            msg = f"cannot go below {self.low}"
        elif self.low is None:
            msg = f"cannot exceed {self.high}"
        else:
            msg = f"must be between {self.low} and {self.high}"

        return msg


class OptionChoiceError(OptionError, t.Generic[OptionTV]):
    """
    Raised when an argument is not one of the choices set by the `Option`.
    """
    def __init__(
        self,
        node: scrolls.ASTNode,
        bad_choice: OptionTV,
        choices: t.Sequence[OptionTV]
    ):
        super().__init__(node)
        self.bad_choice: OptionTV = bad_choice
        self.choices: t.Sequence[OptionTV] = choices

    def __str__(self) -> str:
        choices_str = ", ".join([str(choice) for choice in self.choices])
        return f"has bad value '{self.bad_choice}', must be one of {choices_str}"


class OptionConversionError(OptionError):
    """
    Raised when an option fails to convert to the type set by the `Option`.
    """
    def __init__(
        self,
        node: scrolls.ASTNode,
        cause: Exception
    ):
        super().__init__(node)
        self.cause = cause

    def __str__(self) -> str:
        return str(self.cause)


class OptionRequiredMissingError(Exception):
    """
    Raised when required argument is missing.
    """
    def __str__(self) -> str:
        return "is a required argument that is missing"


class OptionModifier(enum.Enum):
    """
    Enum describing different possible parsing methods used by callbase.
    """

    NONE = 0
    """
    The default. Only one argument is consumed.
    """

    GREEDY = 1
    """
    Arguments are consumed and added to a list until either arguments are exhausted,
    or an argument fails to convert.
    """

    CONSUME_REST = 2
    """
    Consumes the rest of the passed arguments as a single string, joined by spaces.
    If a CONSUME_REST `Option` is used:
    
    - It must be the last `Option`.
    - It must be of type `str`.
    """


class CallBaseCallHandler(scrolls.CallbackCallHandler[T_co]):
    """
    The primary `scrolls.interpreter.CallHandler` implementation for callbase.
    Only `CallBase` subclasses may be added to this handler. See
    [Basic Usage](#basic-usage)
    """

    def __init__(self) -> None:
        super().__init__()
        self._consume_rest_triggers: t.MutableMapping[str, int] = {}

    def add_call(self, name: str, call: scrolls.ScrollCallback[T_co]) -> None:
        # Disallow non-callbase additions.
        # This violates LSP, but the Scrolls core never calls add_call, so it's fine for now :beanos:
        if not isinstance(call, CallBase):
            raise TypeError("Calls added to CallBaseCallHandler must be a type deriving scrolls.commands.CallBase")

        super().add_call(name, call)

    # TODO add remove_callbase
    def add_callbase(self, cmd: 'CallBase[T_co]') -> 'CallBase[T_co]':
        """
        Add a `CallBase` instance to this handler. Automatically handles setting
        up aliases and consume rest triggers. If you want to bypass this automatic
        behavior, see `CallBaseCallHandler.add_call`.
        """
        self.add_call(cmd.name, cmd)

        for alias in cmd.aliases:
            self.add_alias(alias, cmd.name)

        # Set up consume_rest_triggers, which change the behavior of the tokenizer
        # for commands that specify consume_rest.
        if cmd.options and cmd.options[-1].modifier == OptionModifier.CONSUME_REST:
            non_rest_count = len(cmd.options) - 1
            self._consume_rest_triggers[cmd.name] = non_rest_count
            for alias in cmd.aliases:
                self._consume_rest_triggers[alias] = non_rest_count

        return cmd

    def all_callbase(self) -> t.Sequence['CallBase']:
        """
        Get all `CallBase` instances added to this handler.
        """
        # Safe to cast here, since adding non-callbase calls is not allowed.
        return [t.cast(CallBase, cmd) for cmd in self.calls.values()]

    @property
    def consume_rest_triggers(self) -> t.Mapping[str, int]:
        """
        Get the consume rest triggers for all `CallBase` instances attached
        to this handler. This must be passed into the `scrolls.ast.Tokenizer`
        used to tokenize a script. If using `scrolls.interpreter.Interpreter.run`,
        this must be passed into the `consume_rest_triggers` argument.
        """
        return self._consume_rest_triggers


class CallBase(abc.ABC, t.Generic[T_co]):
    """
    The base `CallBase` class. To use, subclass and implement the `CallBase.invoke`
    method.

    Args:
        name: The name of the call.
        description: A short description of the call.
        aliases: A sequence of alternate names for the call.
        hidden: Hint to help displays that this call should be hidden.
    """
    def __init__(
        self,
        name: str,
        description: str,
        aliases: t.Sequence[str] = (),
        hidden: bool = False
    ):
        self.name = name
        self.description = description
        self.help = ""
        self.aliases = aliases
        self.hidden = hidden

        self.options: t.MutableSequence[Option] = []

    def add_option(self, option: 'Option') -> None:
        """
        Add an option to this callbase.
        """
        if self.options and self.options[-1].modifier == OptionModifier.CONSUME_REST:
            raise ValueError("Cannot add options after CONSUME_REST")

        self.options.append(option)

    def set_help(self, help: str) -> None:
        """
        Set a long help text for this call.
        """
        self.help = help

    def convert_options(self, context: scrolls.InterpreterContext) -> t.Sequence[t.Any]:
        """
        Using the `Option` instances added to this call, parse the arguments contained
        in the passed context object.
        """
        converted_opts = []

        args = context.args
        nodes = context.arg_nodes

        idx = 0

        for option in self.options:
            if idx in nodes:
                # Update current_node for error reporting purposes, but only if idx is pointing to
                # a valid node. idx may be greater than the max if we're consuming a non-required
                # option the user didn't specify.
                context.current_node = nodes[idx]

            try:
                if option.modifier == OptionModifier.CONSUME_REST:
                    if not args:
                        raise OptionRequiredMissingError()

                    converted_opts.append(args[0])
                    break

                _result, num_consumed = consume_option(option, args, nodes, idx)
            except OptionRequiredMissingError as e:
                raise scrolls.InterpreterError(
                    context,
                    f"{option.name} {e}"
                )
            except OptionError as e:
                raise scrolls.InterpreterError(
                    context,
                    f"{option.name}: {e}"
                )

            if len(_result) == 1 and option.modifier != OptionModifier.GREEDY:
                result = _result[0]
            else:
                result = _result

            converted_opts.append(result)

            args = args[num_consumed:]
            idx += num_consumed

        return converted_opts

    @abc.abstractmethod
    def invoke(self, context: scrolls.InterpreterContext, args: t.Sequence[t.Any]) -> T_co:
        """
        Invoke this call.
        """
        ...

    def __call__(self, context: scrolls.InterpreterContext) -> T_co:
        return self.invoke(context, self.convert_options(context))


class CallbackCallBase(CallBase[CallBaseCallbackReturnTV]):
    """
    A basic callbase that just invokes a given callback. Used for the make_callback_command decorator.
    """
    def __init__(
        self,
        name: str,
        description: str,
        callback: CallBaseCallbackT,
        aliases: t.Sequence[str] = (),
        hidden: bool = False
    ):
        super().__init__(name, description, aliases, hidden)
        self.callback = callback

    def invoke(self, context: scrolls.InterpreterContext, args: t.Sequence[t.Any]) -> CallBaseCallbackReturnTV:
        # mypy complains Any is being returned here - odd, but I can confirm this is not the case, so cast it.
        return t.cast(CallBaseCallbackReturnTV, self.callback(context, args))


def make_callbase(
    name: str,
    description: str,
    aliases: t.Sequence[str] = (),
    hidden: bool = False
) -> t.Callable[[CallBaseCallbackT], CallbackCallBase[CallBaseCallbackReturnTV]]:
    """
    Decorator that creates a `CallbackCallBase` out of a function.

    **Usage Example**
    ```py
    import scrolls
    from scrolls.ext import callbase
    from typing import Sequence, Any

    @callbase.make_callbase(
        name="mycall",
        description="This is an example.",
        aliases=["mycall_alias", "foobar"]
    )
    def call(context: scrolls.InterpreterContext, args: Sequence[Any]) -> None:
        # implementation here
        ...
    ```

    See [Basic Usage](#basic-usage) for a more complete usage example.

    Args:
        name: The name of the call.
        description: A short description of the call.
        aliases: A sequence of alternate names for the call.
        hidden: Hint to help displays that this call should be hidden.
    """
    def decorate(callback: CallBaseCallbackT) -> CallbackCallBase[CallBaseCallbackReturnTV]:
        return CallbackCallBase(
            name,
            description,
            callback,
            aliases,
            hidden
        )

    return decorate


@dataclasses.dataclass
class Option(t.Generic[OptionTV]):
    """
    An option for a `CallBase`. Controls parsing for arguments when a call is invoked.
    Options may be added to a `CallBase` through `CallBase.add_option`, or used as
    a decorator for convenience. See [Basic Usage](#basic-usage).

    Args:
        name: The name of the option.
        type: A type to convert the str option to.
        minimum: The minimum bound for this option, if type is `int` or `float`.
        default: The default value for this option. If specified, this option is
            not required.
        maximum: The maximum bound for this option, if type is `int` or `float`.
        modifier: Selects the option parsing behavior. See `OptionModifier`.
        choices: Limits this option to a number of distinct choices.
    """

    name: str
    type: t.Type[OptionTV] = t.cast(t.Type[OptionTV], str)  # T is allowed to be str, but mypy complains. Cast it.
    minimum: t.Optional[numbers.Real] = None
    default: t.Optional[OptionTV] = None
    maximum: t.Optional[numbers.Real] = None
    modifier: OptionModifier = OptionModifier.NONE
    choices: t.Sequence[OptionTV] = ()

    def verify_option(self) -> None:
        """
        Verifies this option was constructed correctly. Raises a `TypeError` if not.
        """
        bad_consume_rest = (
            self.modifier == OptionModifier.CONSUME_REST and
            not self.type == str
        )
        if bad_consume_rest:
            raise TypeError("OptionModifier.CONSUME_REST can only be used on type str")

    def __call__(self, cmd: CallBase) -> CallBase:
        """Enables Options to be used as decorators directly."""

        self.verify_option()
        cmd.add_option(self)
        return cmd

    def convert_arg(self, arg: str, node: scrolls.ASTNode) -> OptionTV:
        """
        Convert a string to the type specified for this option, and check:

        - `choices`
        - `maximum`
        - `minimum`
        """
        logger.debug(f"Attempt to convert {arg} to {self.type.__name__}")

        try:
            arg_converted = self.type(arg)
        except Exception as e:
            raise OptionConversionError(node, e) from e

        if isinstance(arg_converted, numbers.Real):
            if self.minimum is not None or self.maximum is not None:
                rangelimit(node, self.minimum, arg_converted, self.maximum)

        if self.choices and arg_converted not in self.choices:
            raise OptionChoiceError(node, arg_converted, self.choices)

        return arg_converted


def consume_option(
    option: Option[OptionTV],
    args: t.Sequence[str],
    nodes: scrolls.ArgSourceMap[scrolls.ASTNode],
    arg_num: int
) -> tuple[t.Sequence[OptionTV], int]:
    """
    Consume arguments from a list of strings according to the parsing rules
    in `Option`.

    Args:
        option: The option to parse.
        args: The arguments to consume from.
        nodes: A map of argument numbers to source `scrolls.ast.ASTNode` instances.
        arg_num: The arg number of `args[0]`.

    Returns:
        A tuple containing the sequence of converted options, and the number of
        arguments consumed.
    """
    logger.debug(f"consume_option: args={str(args)}")

    idx = 0

    if not args and option.default is not None:
        logger.debug(f"{option.name}: return default arg {option.default}")
        return [option.default], 1
    elif not args:
        raise OptionRequiredMissingError()

    converted_args: t.MutableSequence[OptionTV] = []

    while idx < len(args):
        arg = args[idx]
        node = nodes[arg_num + idx]

        try:
            converted_arg = option.convert_arg(arg, node)

            if option.modifier == OptionModifier.NONE:
                return [converted_arg], 1

            converted_args.append(converted_arg)
            idx += 1
        except OptionError as e:
            if option.modifier == OptionModifier.NONE:
                logger.debug(f"Conversion failed.")
                raise
            else:
                # For GREEDY, bail on first conversion failure.
                logger.debug(f"GREEDY: Got {str(converted_args)}")
                return converted_args, idx

    logger.debug(f"GREEDY: Exhausted arguments. Got {str(converted_args)}")
    return converted_args, idx


def set_help(
    help: str
) -> t.Callable[[CallBase], CallBase]:
    """
    Sets the long help text for a `CallBase` instance.
    """
    def decorate(f: CallBase) -> CallBase:
        f.set_help(help)

        return f

    return decorate