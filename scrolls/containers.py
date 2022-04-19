"""
Container utilities.
"""

import typing as t

from . import interpreter

T_co = t.TypeVar("T_co", covariant=True)


class DecoratorInstanceList(list[T_co]):
    """
    A list that may be used as a decorator to append an instance
    of the class decorated. The `__init__` method of the class decorated
    must be able to take no arguments.

    Example usage:

    ```py
    instancelist = DecoratorInstanceList()

    @instancelist
    class A:
        ...
    ```
    """
    def __call__(self, x: t.Type[T_co]) -> t.Type[T_co]:
        self.append(x())
        return x


class DecoratorInterpreterConfig:
    """
    A utility configuration object for class-based handler configuration.

    Example usage:

    ```py
    config = DecoratorInterpreterConfig()

    @config.commandhandler
    class MyCommandHandler(scrolls.CommandHandler):
        ...

    @config.controlhandler
    class MyControlHandler(scrolls.ControlHandler):
        ...

    ...

    interpreter = scrolls.Interpreter()
    config.configure(interpreter)
    ```
    """
    def __init__(self) -> None:
        self.initializer: DecoratorInstanceList[interpreter.Initializer] = DecoratorInstanceList()
        """Register an instance of the decorated class as an initializer."""

        self.controlhandler: DecoratorInstanceList[interpreter.CallHandler[None]] = DecoratorInstanceList()
        """Register an instance of the decorated class as a control handler."""

        self.commandhandler: DecoratorInstanceList[interpreter.CallHandler[None]] = DecoratorInstanceList()
        """Register an instance of the decorated class as a command handler."""

        self.expansionhandler: DecoratorInstanceList[interpreter.CallHandler[str]] = DecoratorInstanceList()
        """Register an instance of the decorated class as an expansion handler."""

    def configure(self, interp: interpreter.Interpreter) -> None:
        """
        Configure an interpreter with this config.
        """
        interp.initializers.add_all(self.initializer)
        interp.control_handlers.add_all(self.controlhandler)
        interp.command_handlers.add_all(self.commandhandler)
        interp.expansion_handlers.add_all(self.expansionhandler)
