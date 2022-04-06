#
# A basic command handler implementation for scrolls.
#
import abc
import dataclasses
import enum
import logging
import numbers
import typing as t

from . import ast, interpreter

logger = logging.getLogger(__name__)

T = t.TypeVar("T", str, int, float, bool)
CommandCallbackT = t.Callable[[interpreter.InterpreterContext, t.Sequence[t.Any]], None]


def rangelimit(
    node: ast.ASTNode,
    low: t.Optional[numbers.Real],
    val: numbers.Real,
    high: t.Optional[numbers.Real]
) -> None:
    """Check if val is between low and high. If not, raise a RangeLimitError."""

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
    def __init__(self, node: ast.ASTNode):
        self.node = node


class OptionRangeLimitError(OptionError):
    def __init__(
        self,
        node: ast.ASTNode,
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


class OptionChoiceError(OptionError, t.Generic[T]):
    def __init__(
        self,
        node: ast.ASTNode,
        bad_choice: T,
        choices: t.Sequence[T]
    ):
        super().__init__(node)
        self.bad_choice: T = bad_choice
        self.choices: t.Sequence[T] = choices

    def __str__(self) -> str:
        choices_str = ", ".join([str(choice) for choice in self.choices])
        return f"has bad value '{self.bad_choice}', must be one of {choices_str}"


class OptionConversionError(OptionError):
    def __init__(
        self,
        node: ast.ASTNode,
        cause: Exception
    ):
        super().__init__(node)
        self.cause = cause

    def __str__(self) -> str:
        return str(self.cause)


class OptionRequiredMissingError(Exception):
    def __str__(self) -> str:
        return "is a required argument that is missing"


class OptionModifier(enum.Enum):
    NONE = 0
    GREEDY = 1
    CONSUME_REST = 2


class GenericCommandHandler(interpreter.CallbackCallHandler[None]):
    def __init__(self) -> None:
        super().__init__()
        self._consume_rest_triggers: t.MutableMapping[str, int] = {}

    def add_call(self, name: str, command: interpreter.ScrollCallback[None]) -> None:
        # Disallow non-command additions.
        if not isinstance(command, Command):
            raise TypeError("Commands added to GenericCommandHandler must be a type deriving scrolls.Command")

        super().add_call(name, command)

    # TODO add remove_command
    def add_command(self, cmd: 'Command') -> 'Command':
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

    # Get all commands as Command objects
    def all_commands(self) -> t.Sequence['Command']:
        # Safe to cast here, since adding non-command calls is not allowed.
        return [t.cast(Command, cmd) for cmd in self.calls.values()]

    @property
    def consume_rest_triggers(self) -> t.Mapping[str, int]:
        return self._consume_rest_triggers


class Command(abc.ABC):
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
        if self.options and self.options[-1].modifier == OptionModifier.CONSUME_REST:
            raise ValueError("Cannot add options after CONSUME_REST")

        self.options.append(option)

    def set_help(self, help: str) -> None:
        self.help = help

    def convert_options(self, context: interpreter.InterpreterContext) -> t.Sequence[t.Any]:
        converted_opts = []

        args = context.args
        nodes = context.arg_nodes

        idx = 0

        for option in self.options:
            if nodes:
                context.current_node = nodes[idx]

            try:
                if option.modifier == OptionModifier.CONSUME_REST:
                    if not args:
                        raise OptionRequiredMissingError()

                    converted_opts.append(args[0])
                    break

                _result, num_consumed = consume_option(option, args, nodes, idx)
            except OptionRequiredMissingError as e:
                raise interpreter.InterpreterError(
                    context,
                    f"{option.name} {e}"
                )
            except OptionError as e:
                raise interpreter.InterpreterError(
                    context,
                    f"{option.name}: {e}"
                )

            if len(_result) == 1:
                result = _result[0]
            else:
                result = _result

            converted_opts.append(result)

            args = args[num_consumed:]
            idx += num_consumed

        return converted_opts

    @abc.abstractmethod
    def invoke(self, context: interpreter.InterpreterContext, args: t.Sequence[t.Any]) -> None: ...

    def __call__(self, context: interpreter.InterpreterContext) -> None:
        self.invoke(context, self.convert_options(context))


class CallbackCommand(Command):
    """
    A basic command that just invokes a given callback. Used for the make_callback_command decorator.
    """
    def __init__(
        self,
        name: str,
        description: str,
        callback: CommandCallbackT,
        aliases: t.Sequence[str] = (),
        hidden: bool = False
    ):
        super().__init__(name, description, aliases, hidden)
        self.callback = callback

    def invoke(self, context: interpreter.InterpreterContext, args: t.Sequence[t.Any]) -> None:
        self.callback(context, args)


def make_callback_command(
    name: str,
    description: str,
    aliases: t.Sequence[str] = (),
    hidden: bool = False
) -> t.Callable[[CommandCallbackT], CallbackCommand]:
    def decorate(callback: CommandCallbackT) -> CallbackCommand:
        return CallbackCommand(
            name,
            description,
            callback,
            aliases,
            hidden
        )

    return decorate


@dataclasses.dataclass
class Option(t.Generic[T]):
    name: str
    type: t.Type[T] = t.cast(t.Type[T], str)  # T is allowed to be str, but mypy complains. Cast it.
    minimum: t.Optional[numbers.Real] = None
    default: t.Optional[T] = None
    maximum: t.Optional[numbers.Real] = None
    modifier: OptionModifier = OptionModifier.NONE
    choices: t.Sequence[T] = ()

    def verify_option(self) -> None:
        bad_consume_rest = (
            self.modifier == OptionModifier.CONSUME_REST and
            not self.type == str
        )
        if bad_consume_rest:
            raise TypeError("OptionModifier.CONSUME_REST can only be used on type str")

    def __call__(self, cmd: Command) -> Command:
        """Enables Options to be used as decorators directly."""
        self.verify_option()
        cmd.add_option(self)
        return cmd

    def convert_arg(self, arg: str, node: ast.ASTNode) -> T:
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
    option: Option[T],
    args: t.Sequence[str],
    nodes: interpreter.ArgSourceMap[ast.ASTNode],
    arg_num: int
) -> tuple[t.Sequence[T], int]:
    logger.debug(f"consume_option: args={str(args)}")

    idx = 0

    if not args and option.default is not None:
        logger.debug(f"{option.name}: return default arg {option.default}")
        return [option.default], 1
    elif not args:
        raise OptionRequiredMissingError()

    converted_args: t.MutableSequence[T] = []

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
) -> t.Callable[[Command], Command]:
    def decorate(f: Command) -> Command:
        f.set_help(help)

        return f

    return decorate