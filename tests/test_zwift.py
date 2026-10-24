import json
import time

import pytest
import responses

from scale2zwift.zwift import PROFILE_URL, TOKEN_URL, WRITE_URL, ZwiftAuthError, ZwiftClient, ZwiftError

PROFILE = {"id": 123, "firstName": "Test", "weight": 75000, "height": 1800}
TOKENS = {"access_token": "a1", "refresh_token": "r1", "expires_in": 300}


def client(**kwargs):
    return ZwiftClient("rider@example.com", "not-a-real-password", **kwargs)


@responses.activate
def test_login_and_update_weight():
    saved = []
    responses.post(TOKEN_URL, json=TOKENS)
    responses.get(PROFILE_URL, json=PROFILE)
    responses.put(WRITE_URL.format(profile_id=123), status=204)
    responses.get(PROFILE_URL, json={**PROFILE, "weight": 74500})

    assert client(on_tokens=saved.append).set_weight(74500) is True

    put = responses.calls[2].request
    assert json.loads(put.body) == {**PROFILE, "weight": 74500}
    assert put.headers["Authorization"] == "Bearer a1"
    assert saved and saved[0]["refresh_token"] == "r1"


@responses.activate
def test_no_write_when_weight_already_matches():
    responses.post(TOKEN_URL, json=TOKENS)
    responses.get(PROFILE_URL, json=PROFILE)
    assert client().set_weight(75000) is False
    assert not any(c.request.method == "PUT" for c in responses.calls)


@responses.activate
def test_update_not_reflected_is_an_error():
    responses.post(TOKEN_URL, json=TOKENS)
    responses.get(PROFILE_URL, json=PROFILE)
    responses.put(WRITE_URL.format(profile_id=123), status=200)
    with pytest.raises(ZwiftError, match="did not change"):
        client().set_weight(74000)


@responses.activate
def test_bad_password():
    responses.post(TOKEN_URL, status=401, json={"error": "invalid_grant"})
    with pytest.raises(ZwiftAuthError):
        client().login()


@responses.activate
def test_expired_token_is_refreshed():
    responses.post(TOKEN_URL, json={**TOKENS, "access_token": "a2"})
    responses.get(PROFILE_URL, json=PROFILE)
    old = {"access_token": "a0", "refresh_token": "r0", "expires_at": time.time() - 10}
    client(tokens=old).get_profile()
    assert "grant_type=refresh_token" in responses.calls[0].request.body
    assert responses.calls[1].request.headers["Authorization"] == "Bearer a2"


@responses.activate
def test_401_falls_back_to_password_login():
    responses.get(PROFILE_URL, status=401)
    responses.post(TOKEN_URL, status=400)  # refresh token rejected
    responses.post(TOKEN_URL, json=TOKENS)  # password login
    responses.get(PROFILE_URL, json=PROFILE)
    valid = {"access_token": "a0", "refresh_token": "r0", "expires_at": time.time() + 300}
    assert client(tokens=valid).get_profile()["id"] == 123
    assert "grant_type=password" in responses.calls[2].request.body


def test_rejects_out_of_range_weight():
    with pytest.raises(ZwiftError, match="30-300"):
        client().set_weight(5000)
