""" Exceptions for Dahua package """
from typing import TYPE_CHECKING
from urllib.request import Request

if TYPE_CHECKING:
    from .device import Device

class DahuaException(BaseException):
    def __init__(self, device: 'Device', *args) -> None:
        super().__init__(device, *args)
        self.device = device


class ProtocolException(DahuaException):
    default_code = None
    default_reason = None

    def __init__(self, device: 'Device', request_object: Request = None, code: int = None, reason: str = None, *args):
        self.device = device
        self.code = self.default_code if code is None else code
        self.reason = self.default_reason if reason is None else reason
        self.request_object = request_object

        # @TODO: check whether this call should be at the bottom
        if self.request_object:
            super().__init__(device, self.code, self.reason, request_object.full_url)
        else:
            super().__init__(device, self.code, self.reason)

    def __str__(self):
        message = f'Protocol error {self.code}: {self.reason}'
        if self.request_object:
            return message + f' ({self.request_object.full_url})'
        return message

    def __int__(self):
        return self.code

class UnauthorizedException(ProtocolException):
    default_code = 401
    default_reason = 'Unauthorized'
