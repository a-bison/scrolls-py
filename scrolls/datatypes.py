"""
Datatype conversions for Scrolls. This module defines tools for writing `scrolls.interpreter.CallHandler` implementations
that act like the built-in ones. Including:

- Implicit type conversion logic.
- Built-in constants.
- Argument length checks.

See `scrolls.builtins` for example usages of this module.

.. NOTE::
    `NumT` and `NumU` are type variables that refer to `numbers.Real` or any subtype (`int`, `float`, etc.).
"""

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


TRUE: str = "1"
"""The string considered TRUE by builtin boolean functions (`"1"`)."""

FALSE: str = "0"
"""The string considered FALSE by builtin boolean functions (`"0"`)."""


class NumericType(enum.Enum):
    """
    Describes the type of number returned from a scrolls function. To be paired with `int` or `float`.
    """
    INT = enum.auto()
    FLOAT = enum.auto()
    NONE = enum.auto()


NumT = t.TypeVar('NumT', bound=numbers.Real, covariant=True)
NumU = t.TypeVar('NumU', bound=numbers.Real, covariant=True)
ScrollNumT = t.Tuple[t.Union[int, float], NumericType]
UnaryNumOpT = t.Callable[[NumT], NumT]
BinaryNumOpT = t.Callable[[NumT, NumU], t.Union[NumT, NumU]]
UnaryBoolOpT = t.Callable[[bool], bool]
BinaryBoolOpT = t.Callable[[bool, bool], bool]


def str_to_bool(x: str) -> bool:
    """`"0"` is interpreted as `FALSE`, everything else is `TRUE`."""
    return not x == FALSE


def bool_to_str(b: bool) -> str:
    """
    Convert a boolean to a Scrolls boolean string.

    Returns:
        `TRUE` if b is `True`, otherwise `FALSE`.
    """
    return TRUE if b else FALSE


def toint(n: t.Union[int, float]) -> int:
    """Force a number to be an integer."""
    return int(n)


def tofloat(n: t.Union[int, float]) -> float:
    """Force a number to be a float."""
    return float(n)


def str_to_numeric(s: str) -> t.Tuple[t.Optional[t.Union[int, float]], NumericType]:
    """
    Convert a Scrolls numeric string to a number.

    Returns:
        - `(int, NumericType.INT)` if `s` is an integer
        - `(float, NumericType.FLOAT)` if `s` is a float
        - `(None, NumericType.NONE)` if no number could be parsed.
    """
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
    """
    Convert a Scrolls numeric string to a number, raising an error if no number is found.

    Returns:
        - `(int, NumericType.INT)` if `s` is an integer
        - `(float, NumericType.FLOAT)` if `s` is a float

    Raises:
        `scrolls.interpreter.InterpreterError` if no number is found.
    """
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
) -> t.Tuple[t.Sequence[t.Union[int, float]], NumericType]:
    """
    Convert a sequence of strings to numbers.

    Returns:
        - `(t.Sequence[int], NumericType.INT)` if all `strs` could be parsed as integers.
        - `(t.Sequence[float], NumericType.FLOAT)` if all `strs` could be parsed as numbers, but at least one is a float.
          In this case, *all* returned numbers will be floats.

    Raises:
        `scrolls.interpreter.InterpreterError` if any of `strs` could not be parsed as a number.
    """
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
    """
    Require that the current call was passed at least `n` arguments.

    Raises:
        `scrolls.interpreter.InterpreterError` if this is not the case.
    """
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
    """
    Apply a unary numeric operator to the arguments of the current call. An example of an operator would be
    negation, as in the `-` in `-4`.
    """
    require_arg_length(context, 1)

    n, t = require_numeric(context, context.args[0])
    return op(n), t


def apply_binary_num_op(
    context: interpreter.InterpreterContext,
    op: BinaryNumOpT,
    args: t.Sequence[str] = (),
    len_check: bool = False
) -> ScrollNumT:
    """
    Apply a binary numeric operator to the arguments of the current call. An example of such an operator would be
    addition, i.e. `3 + 4`.

    Args:
        context: The current interpreter context.
        op: The numeric operator, as a function.
        args: If not empty, override `context.args` with this sequence.
        len_check: Normally, there must be at least 2 arguments. If `len_check` is `False`, this check will be skipped.

    Returns:
        - `(int, NumericType.INT)` if all operands are integers.
        - `(float, NumericType.FLOAT)` if one or both operands are floats.
    """
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
    """
    Apply a binary operator to a sequence of inputs through reduction. Say we have a binary operator `+`, and inputs
    `1 2 3 4 5`. Then, the output would be `((((1 + 2) + 3) + 4) + 5)`. This is also known as a
    [left fold](https://en.wikipedia.org/wiki/Fold_(higher-order_function)).

    Args:
        context: The current interpreter context.
        reduce_op: The numeric operator, as a function.
        args: If not empty, override `context.args` with this sequence.
        len_check: Normally, there must be at least 1 argument. If `len_check` is `False`, this check will be skipped.

    Returns:
        - `(int, NumericType.INT)` if all operands are integers.
        - `(float, NumericType.FLOAT)` if at least one operand is float.

    Related:
        - [`functools.reduce`](https://docs.python.org/3/library/functools.html#functools.reduce)
    """
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
    """
    Implements a mass operator with two binary numeric operators. This is used to implement operations like mass
    subtraction:

    ```scrolls
    print "10 - 4 - 2 - 5 is" $(- 10 4 2 5)
    ```

    A mass operator is characterized by a reduction step of all right-hand arguments, followed by a finishing step. The
    mass subtraction operator above is calculated like so: `10 - ((4 + 2) + 5)`. `reduce_op` is `+`, and `final_op` is
    `-`.

    Args:
        context: The current interpreter context.
        reduce_op: A numeric operator, as a function. Used in the reduction step.
        final_op: A numeric operator, as a function. Used to finish the calculation.
        len_check: Normally, there must be at least 1 argument. If `len_check` is `False`, this check will be skipped.

    Returns:
        - `(int, NumericType.INT)` if all operands are integers.
        - `(float, NumericType.FLOAT)` if at least one operand is float.

    Related:
        - `apply_reduce_binary_num_op`
    """
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
    """
    Apply a unary boolean operator to the arguments of the current call. For example, `not`.
    """
    if len_check:
        require_arg_length(context, 1)

    return op(str_to_bool(context.args[0]))


def apply_binary_bool_op(
    context: interpreter.InterpreterContext,
    op: BinaryBoolOpT,
    len_check: bool = False
) -> bool:
    """
    Apply a binary boolean operator to the arguments of the current call. For example, `and`, `or`, etc.
    """
    if len_check:
        require_arg_length(context, 2)

    return op(str_to_bool(context.args[0]), str_to_bool(context.args[1]))


def apply_reduce_bool_op(
    context: interpreter.InterpreterContext,
    op: BinaryBoolOpT,
    len_check: bool = False
) -> bool:
    """
    Apply a binary boolean operator to the arguments of the current call by reduction. See `apply_reduce_binary_num_op`.
    """
    if len_check:
        require_arg_length(context, 2)

    result = functools.reduce(op, [str_to_bool(s) for s in context.args])
    return result
