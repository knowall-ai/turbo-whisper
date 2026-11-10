import json

import httpx
import pytest

from turbo_whisper.polish import LocalPolisher, local_endpoint


def polisher(responses, requests):
    values = iter(responses)

    def response(request):
        assert request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(next(values))}}]}
        )

    return LocalPolisher(
        "http://localhost:8080/v1/chat/completions",
        "local-test",
        transport=httpx.MockTransport(response),
    )


def test_full_session_correction_preserves_exact_unfinished_tail():
    requests = []
    client = polisher([{"incomplete": True}, {"text": "She goes to work."}], requests)
    text = "She go to work. Because the train was delayed."
    result = client.polish(text)
    assert result.text == "She goes to work. Because the train was delayed."
    assert result.incomplete_tail == "Because the train was delayed."
    assert result.status == "incomplete"
    assert json.loads(requests[1]["messages"][1]["content"]) == {"dictation": "She go to work."}
    assert json.loads(requests[0]["messages"][1]["content"])["context"] == text


def test_standalone_fragment_never_reaches_rewriter():
    requests = []
    result = polisher([{"incomplete": True}], requests).polish("If we could move the meeting to.")
    assert result.status == "incomplete"
    assert result.text == result.incomplete_tail == "If we could move the meeting to."
    assert len(requests) == 1


@pytest.mark.parametrize(
    "source,changed",
    [
        ("The reports was ready yesterday.", "The report was ready yesterday."),
        ("Maya did not approve invoice 1042.", "Maya did approve invoice 1042."),
        ("Maya approved invoice 1042.", "Maya approved invoice 1043."),
        ("Maya approved it.", "Maria approved it."),
        ("Please send the final report tomorrow.", ""),
        ("Please send the final report tomorrow.", "   "),
        ("She is ready.", "She was ready."),
        ("Please send it. Keep a copy.", "Please send it."),
        ("The cost is $40.", "The cost is €40."),
        ("Maya 🙂 is ready.", "Maya is ready."),
        ("Did Maya approve it?", "Maya did approve it."),
    ],
)
def test_unsafe_or_omitted_content_is_held_for_review(source, changed):
    result = polisher([{"incomplete": False}, {"text": changed}], []).polish(source)
    assert result.status == "review"
    assert result.text == source
    assert result.proposed_text == changed.strip()


@pytest.mark.parametrize(
    "source,corrected",
    [
        ("The reports was ready yesterday.", "The reports were ready yesterday."),
        ("She go to work", "She goes to work."),
        ("Please send the final report tomorrow.", "Please send the final report tomorrow."),
        ("Maya did not approve invoice 1042.", "Maya did not approve invoice 1042."),
    ],
)
def test_conservative_grammar_and_complete_imperatives(source, corrected):
    result = polisher([{"incomplete": False}, {"text": corrected}], []).polish(source)
    assert result.status == "polished"
    assert result.text == corrected


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/correct",
        "http://192.168.1.2:8080",
        "http://localhost@evil.invalid/v1",
        "http://localhost/x?remote=1",
    ],
)
def test_polishing_cannot_send_dictation_off_device(endpoint):
    with pytest.raises(ValueError):
        local_endpoint(endpoint)


def test_redirect_and_invalid_json_keep_original_text():
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://example.invalid/private"})

    client = LocalPolisher(
        "http://127.0.0.1:8080/v1/chat/completions",
        "local-test",
        transport=httpx.MockTransport(redirect),
    )
    result = client.polish("A complete thought.")
    assert result.text == "A complete thought."
    assert result.status == "review"
    assert len(requests) == 1


def test_bad_classifier_schema_does_not_finalize_text():
    result = polisher([{"incomplete": "false"}], []).polish("The blue folder.")
    assert result.text == "The blue folder."
    assert result.status == "review"
