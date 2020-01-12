"""Helpers for Dahua package"""
from typing import Union, Any, Dict
from asyncio import gather, Future

from dotty_dict import dotty


async def gather_dict(tasks, **kwargs):
    return dict(zip(tasks.keys(), await gather(*tasks.values(), **kwargs)))


def str_value_to_type(value: str) -> Union[None, str, int, bool]:
    lower_value = value.lower()
    if lower_value == 'true':
        return True
    elif lower_value == 'false':
        return False
    elif lower_value == 'null':
        return None
    elif value.isdigit():
        return int(value)
    return value


def dict_from_dotted_str(data: str) -> dict:
    dot = dotty()
    for line in data.splitlines():
        key, value = line.split('=', 1)
        dot[key.replace('[', '.').replace(']', '')] = str_value_to_type(value)
    return dot.to_dict()
