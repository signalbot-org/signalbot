import pytest

from signalbot import SignalBotError
from tests.unit.conftest import TestCommon


class TestUsernameValidation(TestCommon):
    @pytest.mark.parametrize(
        "username",
        [
            "Usr.99",
            "UserName.99",
            "username.999999999",
            "UserName99.99",
            "_Use_rName99_.99",
            "usernameeeeeeeeeeeeeeeeeeeeeeeee.999999999",
        ],
    )
    def test_valid_username(self, username: str):
        assert self.signal_bot._recipients._is_username(username)

    @pytest.mark.parametrize(
        "username",
        [
            "Us.99",
            "Usr.9",
            ".UserName99",
            ".UserName.99",
            "UserName99",
            "UserName99.",
            "username.9999999999",
            "user@name.999",
            "UserName99.0",
            "UserName99.00",
            "UserName99.000000000",
            ".usernameeeeeeeeeeeeeeeeeeeeeeeeee.99",
        ],
    )
    def test_invalid_username(self, username: str):
        assert not self.signal_bot._recipients._is_username(username)

    @pytest.mark.parametrize(
        "username",
        [
            "UserName.ab",
            "UserName.-12",
            "UserName.1_0",
            "UserName. 12",
            "UserName.١٢",  # non-ASCII digits
            "UserName\n.12",
            "Us\u0661.12",  # non-ASCII digit (Arabic-Indic one) in the name part
        ],
    )
    def test_discriminator_must_be_ascii_digits(self, username: str):
        assert not self.signal_bot._recipients._is_username(username)


class TestResolve(TestCommon):
    @pytest.mark.parametrize(
        "recipient",
        [
            "+4915112345678",
            "11111111-1111-1111-1111-111111111111",
            "UserName.99",
        ],
    )
    def test_contacts_resolve_to_themselves(self, recipient: str):
        assert self.signal_bot._recipients.resolve(recipient) == recipient

    def test_unknown_recipient_raises(self):
        with pytest.raises(SignalBotError):
            self.signal_bot._recipients.resolve("not a recipient")
