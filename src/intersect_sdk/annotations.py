"""
Users annotate their endpoints with this decorator much as they would when
developing a traditional REST API. The decorator allows for users to
declare certain key aspects about their data, without having to delve
into the plumbing which integrates their data into other backing services.
"""

import functools
from enum import Enum, IntEnum
from typing import Any, Callable, Optional, Set

from ._internal.constants import (
    BASE_ATTR,
    BASE_STATUS_ATTR,
    REQUEST_CONTENT,
    RESPONSE_CONTENT,
    RESPONSE_DATA,
    SHUTDOWN_KEYS,
    STRICT_VALIDATION,
)


class IntersectDataHandler(IntEnum):
    """
    What data transfer type do you want to use for handling the request/response?

    Default: MESSAGE
    """

    MESSAGE = 0
    MINIO = 1


class IntersectMimeType(Enum):
    """
    this is an enum which should be publicly exposed to users

    the value should be a MIME type (i.e.
    https://www.iana.org/assignments/media-types/media-types.xhtml
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
    )

    JSON is acceptable for any file which contains non-binary data
    BINARY is acceptable for any file which contains binary data
    """

    JSON = 'application/json'
    STRING = 'text/plain'
    BINARY = 'application/octet-string'


def intersect_message(
    ignore_keys: Optional[Set[str]] = None,
    request_content_type: IntersectMimeType = IntersectMimeType.JSON,
    response_data_transfer_handler: IntersectDataHandler = IntersectDataHandler.MESSAGE,
    # TODO response_content_type may end up being a union
    response_content_type: IntersectMimeType = IntersectMimeType.JSON,
    strict_request_validation: bool = False,
) -> Any:
    """
    Use this annotation to mark your capability method as an entrypoint to external requests.

    A class method marked with this annotation has two requirements:
    1) Excluding the self-reference in the class definition, any additional parameters
       MUST have an entire class hierarchy of the following types (for a comprehensive overview of types, see https://docs.pydantic.dev/latest/concepts/types/):
         - Pydantic's "BaseModel" class.
         - Dataclasses (You can either use Pydantic's or the standard library's)
         - TypedDict
         - NamedTuple
         - primitive types (str, bytes, int, float, bool)
         - None
         - Union/Optional types
         - Iterable/Sequence types (list, deque, set, tuple, frozenset, etc.)
         - Mapping types (dict, Counter, OrderedDict, etc.)
         - most stdlib types, i.e. Decimal, datetime.datetime, pathlib, etc.
         - using typing_extensions "Annotated" type in conjunction with Pydantic's "Field"
         - TODO: Generators are a WORK IN PROGRESS but will eventually represent a streaming function
       You are only allowed to have one additional parameter. Functions without this parameter are assumed to take in no arguments.
       Be sure to specify the parameter type in your function signature!
    2) Your response type MUST have a class hierarchy of the same types as above. Be sure to specify the
       parameter type in your function signature! (If you do not return a response, explicitly mark your return type as "None")

    Example:

    @intersect_message()
    def some_external_function(self, request: MyBaseModelRequest) -> MyBaseModelResponse:
        # be sure to return "MyBaseModelResponse" here

    In general, if you are able to create a service from this class, you should be okay.

    Params:
    ignore_keys: Hashset of keys. The service class maintains a set of keys to ignore, and will ignore
      this function if at least one key is present in the service set.
      By default, all functions will always be allowed.
      You generally only need this if you want to forbid only a subset of functions - use
      "service.shutdown()" to disconnect from INTERSECT entirely.
      In general, you should NOT define this on functions which are just query functions;
      only set this if you are mutating INSTRUMENT or APPLICATION state.
    request_content_type: how to deserialize incoming requests (default: JSON)
    response_content_type: how to serialize outgoing requests (default: JSON)
      NOTE: this doesn't need to be a literal Response message, you can also apply it
      to asynchronous messages

    TODO: since multiple messages (probably all Event messages) can be sent out in a function,
    it may be prudent to define a list of response information in the future

    response_data_transfer_handler: are responses going out through the message, or through another mean
    (i.e. MINIO)?
    strict_request_validation: if this is set to True, use pydantic strict validation - otherwise, use lenient validation (default: False)
      See https://docs.pydantic.dev/latest/concepts/conversion_table/ for more info about this.
    """

    def inner_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Callable:
            return func(*args, **kwargs)

        setattr(wrapper, BASE_ATTR, True)
        setattr(wrapper, REQUEST_CONTENT, request_content_type.value)
        setattr(wrapper, RESPONSE_CONTENT, response_content_type.value)
        setattr(wrapper, RESPONSE_DATA, response_data_transfer_handler.value)
        setattr(wrapper, STRICT_VALIDATION, strict_request_validation)
        setattr(wrapper, SHUTDOWN_KEYS, set(ignore_keys) if ignore_keys else set())

        return wrapper

    return inner_decorator


def intersect_status() -> Any:
    """
    Use this annotation to mark your capability method as a status retrieval function.

    You may ONLY mark ONE function as a status retrieval function. It's advisable to have one.
    """

    def inner_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Callable:
            return func(*args, **kwargs)

        setattr(wrapper, BASE_STATUS_ATTR, True)

        return wrapper

    return inner_decorator