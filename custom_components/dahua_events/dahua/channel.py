from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .device import Device

__all__ = [
    'Channel'
]


class Channel:
    def __init__(self, device: 'Device', number: int, name: str) -> None:
        self._device = device
        self._number = number
        self._name = name

    @property
    def device(self) -> 'Device':
        return self._device

    @property
    def number(self) -> int:
        return self._number

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    def __int__(self):
        return self._number

    def __str__(self):
        return self._name

    def __repr__(self) -> str:
        return '<Dahua:Channel(' + repr(self.device) + ', ' + str(self._number) + ')>'
