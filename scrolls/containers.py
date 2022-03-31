#
# Container utilities.
#

import typing as t

from . import interpreter

T_co = t.TypeVar("T_co", covariant=True)


class DecoratorInstanceList(list[T_co]):
    """
    A list that may be used as a decorator to append an instance
    of the class decorated. The __init__ method of the class decorated
    must be able to take no arguments.
    """
    def __call__(self, x: t.Type[T_co]) -> t.Type[T_co]:
        self.append(x())
        return x


class DecoratorInterpreterConfig:
    def __init__(self) -> None:
        # Note: These have singular names so they look better as decorators
        self.initializer: DecoratorInstanceList[interpreter.Initializer] = DecoratorInstanceList()
        self.controlhandler: DecoratorInstanceList[interpreter.CallHandler[None]] = DecoratorInstanceList()
        self.commandhandler: DecoratorInstanceList[interpreter.CallHandler[None]] = DecoratorInstanceList()
        self.expansionhandler: DecoratorInstanceList[interpreter.CallHandler[str]] = DecoratorInstanceList()

    def configure(self, interp: interpreter.Interpreter) -> None:
        """
        Configure an interpreter with this config.
        """
        interp.initializers.add_all(self.initializer)
        interp.control_handlers.add_all(self.controlhandler)
        interp.command_handlers.add_all(self.commandhandler)
        interp.expansion_handlers.add_all(self.expansionhandler)
