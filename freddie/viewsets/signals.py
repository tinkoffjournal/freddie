from collections import defaultdict
from enum import Enum, unique
from inspect import getmembers
from typing import TYPE_CHECKING, Any, Callable, DefaultDict, List, Tuple, Type

from fastapi import BackgroundTasks


@unique
class Signal(str, Enum):
    POST_SAVE = 'post_save'
    PRE_DELETE = 'pre_delete'
    POST_DELETE = 'post_delete'


if TYPE_CHECKING:
    from typing_extensions import Protocol

    class SignalHandler(Protocol):
        type: Signal

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            ...


else:
    SignalHandler = Callable


SignalsMap = DefaultDict[Signal, List[SignalHandler]]
VIEWSET_SIGNAL_FLAG = 'is_viewset_signal'


def signal(signal_type: Signal) -> Callable:
    def decorator(handler: SignalHandler) -> SignalHandler:
        setattr(handler, VIEWSET_SIGNAL_FLAG, True)
        handler.type = signal_type
        return handler

    return decorator


def get_signals_map(obj: Any) -> SignalsMap:
    signals_map: SignalsMap = defaultdict(list)
    handlers: List[Tuple[str, SignalHandler]] = getmembers(
        obj, lambda member: callable(member) and hasattr(member, VIEWSET_SIGNAL_FLAG)
    )
    for _, handler in handlers:
        signals_map[handler.type].append(handler)
    return signals_map


class SignalDispatcher:
    mapping: SignalsMap
    bg_tasks: BackgroundTasks

    def __init__(self, bg_tasks: BackgroundTasks):
        self.bg_tasks = bg_tasks

    @classmethod
    def setup(cls, mapping: SignalsMap) -> Type['SignalDispatcher']:
        return type(cls.__name__, (cls,), {'mapping': mapping})

    def send(
        self,
        signal_type: Signal,
        obj: Any,
        obj_before_update: Any = None,
        **kwargs: Any,
    ) -> None:
        for handler in self.mapping[signal_type]:
            self.bg_tasks.add_task(handler, obj, obj_before_update=obj_before_update, **kwargs)


post_save = Signal.POST_SAVE
pre_delete = Signal.PRE_DELETE
post_delete = Signal.POST_DELETE
