from signalbot.messages import Quote

AUTHOR = "+490123456789"
QUOTE_TIMESTAMP = 1632576001632


def test_quote_with_attachment():
    quote = Quote.model_validate(
        {
            "id": QUOTE_TIMESTAMP,
            "author": AUTHOR,
            "authorNumber": AUTHOR,
            "authorUuid": "<uuid>",
            "text": "",
            "attachments": [
                {
                    "contentType": "image/jpeg",
                    "filename": "image.jpg",
                    "thumbnail": {
                        "contentType": "image/png",
                        "filename": None,
                        "id": "1qeCjjWOOo9Gxv8pfdCw.png",
                        "isVoiceNote": False,
                        "size": 21035,
                        "width": 150,
                        "height": 150,
                        "caption": None,
                        "uploadTimestamp": QUOTE_TIMESTAMP,
                    },
                }
            ],
        }
    )

    assert quote.id == QUOTE_TIMESTAMP
    assert quote.author == AUTHOR
    assert quote.author_number == AUTHOR
    assert quote.author_uuid == "<uuid>"
    assert quote.text == ""
    assert quote.attachments is not None
    assert len(quote.attachments) == 1
    assert quote.attachments[0].content_type == "image/jpeg"
    assert quote.attachments[0].filename == "image.jpg"


def test_quote_with_text():
    quote = Quote.model_validate(
        {
            "id": QUOTE_TIMESTAMP,
            "author": AUTHOR,
            "authorNumber": AUTHOR,
            "authorUuid": "<uuid>",
            "text": "Ping",
            "attachments": [],
        }
    )

    assert quote.id == QUOTE_TIMESTAMP
    assert quote.author == AUTHOR
    assert quote.author_number == AUTHOR
    assert quote.author_uuid == "<uuid>"
    assert quote.text == "Ping"
    assert quote.attachments is not None
    assert len(quote.attachments) == 0


def test_quote_from_dict():
    quote = Quote.model_validate(
        {
            "id": 123,
            "author": AUTHOR,
            "authorNumber": AUTHOR,
            "authorUuid": "<uuid>",
            "text": "Test quote",
            "attachments": [],
        }
    )

    assert quote.id == 123
    assert quote.author == AUTHOR
    assert quote.author_number == AUTHOR
    assert quote.author_uuid == "<uuid>"
    assert quote.text == "Test quote"
    assert quote.attachments is not None
    assert len(quote.attachments) == 0


def test_quote_no_author_number():
    quote = Quote.model_validate(
        {
            "id": QUOTE_TIMESTAMP,
            "author": AUTHOR,
            "authorUuid": "<uuid>",
            "text": "Ping",
            "attachments": [],
        }
    )

    assert quote.id == QUOTE_TIMESTAMP
    assert quote.author == AUTHOR
    assert quote.author_number is None
    assert quote.author_uuid == "<uuid>"
    assert quote.text == "Ping"
    assert quote.attachments is not None
    assert len(quote.attachments) == 0
