# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass  # noqa: I001
from typing import Any, cast

from agent_framework._workflows._request_info_executor import RequestInfoMessage, RequestResponse
from agent_framework._workflows._checkpoint_encoding import (
    decode_checkpoint_value,
    encode_checkpoint_value,
)
from agent_framework._workflows._typing_utils import is_instance_of


@dataclass(kw_only=True)
class SampleRequest(RequestInfoMessage):
    prompt: str


def test_decode_dataclass_with_nested_request() -> None:
    original = RequestResponse[SampleRequest, str](
        data="approve",
        original_request=SampleRequest(request_id="abc", prompt="prompt"),
        request_id="abc",
    )

    encoded = encode_checkpoint_value(original)
    decoded = cast(RequestResponse[SampleRequest, str], decode_checkpoint_value(encoded))

    assert isinstance(decoded, RequestResponse)
    assert decoded.data == "approve"
    assert decoded.request_id == "abc"
    assert isinstance(decoded.original_request, SampleRequest)
    assert decoded.original_request.prompt == "prompt"


def test_is_instance_of_coerces_request_response_original_request_dict() -> None:
    response = RequestResponse[SampleRequest, str](
        data="approve",
        original_request=SampleRequest(request_id="req-1", prompt="prompt"),
        request_id="req-1",
    )

    # Simulate checkpoint decode fallback leaving a dict
    response.original_request = cast(
        Any,
        {
            "request_id": "req-1",
            "prompt": "prompt",
        },
    )

    assert is_instance_of(response, RequestResponse[SampleRequest, str])
    assert isinstance(response.original_request, SampleRequest)
