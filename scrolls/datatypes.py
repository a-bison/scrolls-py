# Datatype conversions for Scrolls. This whole module is kind of gross, and only exists because
# the interpreter stores everything as a string.

import enum
import functools
import numbers
import typing as t

from . import interpreter

__all__ = (
    "TRUE",
    "FALSE",
    "bool_to_str",
    "str_to_bool",
    "require_arg_length",
    "NumericType",
    "str_to_numeric",
    "require_numeric",
    "require_all_numeric",
    "apply_unary_num_op",
    "apply_binary_num_op",
    "apply_reduce_binary_num_op",
    "apply_mass_binary_num_op",
    "apply_binary_bool_op",
    "apply_unary_bool_op",
    "apply_reduce_bool_op"
)


TRUE = "1"
FALSE = "0"


class NumericType(enum.Enum):
    INT = enum.auto()
    FLOAT = enum.auto()
    NONE = enum.auto()


NumT = t.TypeVar('NumT', bound=numbers.Real, covariant=True)
NumU = t.TypeVar('NumU', bound=numbers.Real, covariant=True)
ScrollNumT = tuple[t.Union[int, float], 'NumericType']
UnaryNumOpT = t.Callable[[NumT], NumT]
BinaryNumOpT = t.Callable[[NumT, NumU], t.Union[NumT, NumU]]

UnaryBoolOpT = t.Callable[[bool], bool]
BinaryBoolOpT = t.Callable[[bool, bool], bool]


def str_to_bool(x: str) -> bool:
    # "0" is interpreted as FALSE, everything else as TRUE.
    return not x == FALSE


def bool_to_str(b: bool) -> str:
    return TRUE if b else FALSE


def toint(n: t.Union[int, float]) -> int:
    return int(n)


def tofloat(n: t.Union[int, float]) -> float:
    return float(n)


def str_to_numeric(s: str) -> tuple[t.Optional[t.Union[int, float]], NumericType]:
    try:
        return int(s), NumericType.INT
    except ValueError as e:
        pass

    try:
        return float(s), NumericType.FLOAT
    except ValueError as e:
        pass

    return None, NumericType.NONE


def require_numeric(context: interpreter.InterpreterContext, s: str) -> ScrollNumT:
    n, t = str_to_numeric(s)

    if n is None:
        raise interpreter.InterpreterError(
            context,
            f"{context.call_name}: {s} is not a valid int or float"
        )

    return n, t


def require_all_numeric(
    context: interpreter.InterpreterContext,
    strs: t.Sequence[str]
) -> tuple[t.Sequence[t.Union[int, float]], NumericType]:

    out = []
    convert_to_float = False
    for s in strs:
        n, t = require_numeric(context, s)
        if t == NumericType.FLOAT:
            convert_to_float = True

        out.append(n)

    if convert_to_float:
        return [float(x) for x in out], NumericType.FLOAT
    else:
        return out, NumericType.INT


def require_arg_length(context: interpreter.InterpreterContext, n: int, args: t.Sequence[str] = ()) -> None:
    if not args:
        args = context.args

    if len(args) < n:
        raise interpreter.InterpreterError(
            context,
            f"{context.call_name} requires at least {n} argument{'' if n == 1 else 's'}"
        )


def apply_unary_num_op(
    context: interpreter.InterpreterContext,
    op: UnaryNumOpT
) -> ScrollNumT:
    require_arg_length(context, 1)

    n, t = require_numeric(context, context.args[0])
    return op(n), t


def apply_binary_num_op(
    context: interpreter.InterpreterContext,
    op: BinaryNumOpT,
    args: t.Sequence[str] = (),
    len_check: bool = False
) -> ScrollNumT:
    if len_check:
        require_arg_length(context, 2)

    if args:
        if len(args) != 2:
            raise interpreter.InternalInterpreterError(
                context,
                f"{context.call_name}: Internal arg pass for binary op had {len(args)} args"
            )
    else:
        args = context.args

    (n1, n2), out_t = require_all_numeric(context, args)
    return op(n1, n2), out_t


def apply_reduce_binary_num_op(
    context: interpreter.InterpreterContext,
    reduce_op: BinaryNumOpT,
    args: t.Sequence[str] = (),
    len_check: bool = False
) -> ScrollNumT:
    if len_check:
        require_arg_length(context, 1)

    if not args:
        args = context.args

    nums, nums_t = require_all_numeric(context, args)

    out = functools.reduce(reduce_op, nums)
    return out, nums_t


def apply_mass_binary_num_op(
    context: interpreter.InterpreterContext,
    reduce_op: BinaryNumOpT,
    final_op: BinaryNumOpT,
    len_check: bool = False
) -> ScrollNumT:
    if len_check and len(context.args) < 2:
        raise interpreter.InterpreterError(
            context,
            f"{context.call_name} requires at least two arguments"
        )

    if len(context.args) == 2:
        # Skip reduction step if only 2 args
        return apply_binary_num_op(context, final_op, len_check=False)

    n1, t1 = require_numeric(context, context.args[0])
    n2, t2 = apply_reduce_binary_num_op(context, reduce_op, context.args[1:], False)

    if t1 != t2:
        n1 = float(n1)
        n2 = float(n2)
        out_t = NumericType.FLOAT
    else:
        out_t = NumericType.INT

    return final_op(n1, n2), out_t


def apply_unary_bool_op(
    context: interpreter.InterpreterContext,
    op: UnaryBoolOpT,
    len_check: bool = False
) -> bool:
    if len_check:
        require_arg_length(context, 1)

    return op(str_to_bool(context.args[0]))


def apply_binary_bool_op(
    context: interpreter.InterpreterContext,
    op: BinaryBoolOpT,
    len_check: bool = False
) -> bool:
    if len_check:
        require_arg_length(context, 2)

    return op(str_to_bool(context.args[0]), str_to_bool(context.args[1]))


def apply_reduce_bool_op(
    context: interpreter.InterpreterContext,
    op: BinaryBoolOpT,
    len_check: bool = False
) -> bool:
    if len_check:
        require_arg_length(context, 2)

    result = functools.reduce(op, [str_to_bool(s) for s in context.args])
    return result
