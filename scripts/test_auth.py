"""Real JOSE signatures with a synthetic local issuer; no production accounts or mail."""
import importlib.util
from pathlib import Path
import json
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
import requests

SPEC = importlib.util.spec_from_file_location('ipvx_auth', Path(__file__).resolve().parents[1] / 'infra/auth.py')
auth = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = auth
SPEC.loader.exec_module(auth)


class FakeProvider(auth.RelcomProvider):
    def __init__(self):
        super().__init__('client-1', 'pool-1')
        self.key = RSAKey.generate_key(2048, parameters={'kid': 'local-test'})
        self.keys = KeySet.import_key_set({'keys': [self.key.as_dict(private=False)]})
        self.overrides = {}
        self.calls = 0
        self.rejected = False
        self.unavailable = False
        self.clock = lambda: 2_000_000_000

    def _jwks(self, force=False):
        return self.keys

    def exchange(self, code, verifier, nonce):
        self.calls += 1
        now = int(self.clock())
        claims = {'iss': auth.ISSUER, 'aud': self.client_id, 'sub': 'synthetic-user',
                  'iat': now, 'exp': now + 3600, 'nonce': nonce, auth.ORG_CLAIM: self.org_id,
                  'email': 'fixture@example.invalid', 'email_verified': True, 'name': 'Synthetic reader',
                  **self.overrides}
        token = jwt.encode({'alg': 'RS256', 'kid': 'local-test'}, claims, self.key)
        user = self.validate_id_token(token, nonce, 'synthetic-access', now=now)
        return user, {'access_token': 'synthetic-access', 'id_token': token}, 3600

    def recheck(self, credentials, user):
        if self.rejected:
            raise auth.AuthFailure()
        if self.unavailable:
            raise auth.ProviderUnavailable()


class Authentication(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.provider = FakeProvider()
        self.now = 2_000_000_000
        self.provider.clock = lambda: self.now
        self.service = auth.AuthService('client-1', 'pool-1', self.directory.name,
                                        provider=self.provider, clock=lambda: self.now)
        self.headers = {'Host': 'ipvx.org'}

    def tearDown(self):
        self.directory.cleanup()

    def login(self, query=''):
        response = self.service.handle('GET', '/auth/login' + query, self.headers)
        self.assertEqual(response.status, 302)
        location = dict(response.headers)['Location']
        parameters = parse_qs(urlsplit(location).query)
        cookie = next(v.split(';')[0] for k, v in response.headers if k == 'Set-Cookie')
        self.assertEqual(parameters['code_challenge_method'], ['S256'])
        self.assertNotIn('offline_access', parameters['scope'][0])
        self.assertEqual(parameters['redirect_uri'], ['https://ipvx.org/auth/callback'])
        self.assertIn('Secure; HttpOnly; SameSite=Lax', dict(response.headers)['Set-Cookie'])
        return parameters, {**self.headers, 'Cookie': cookie}

    def callback(self, parameters, headers):
        return self.service.handle('GET', '/auth/callback?code=synthetic&state=' + parameters['state'][0], headers)

    def authenticated(self):
        params, headers = self.login('?returnTo=%2Faccount.html')
        callback = self.callback(params, headers)
        self.assertEqual(callback.status, 303)
        cookie = next(v.split(';')[0] for k, v in callback.headers
                      if k == 'Set-Cookie' and v.startswith(auth.SESSION_COOKIE + '='))
        return {**self.headers, 'Cookie': cookie}

    def test_login_callback_session_and_encrypted_storage(self):
        headers = self.authenticated()
        response = self.service.handle('GET', '/auth/session', headers)
        value = json.loads(response.body)
        self.assertTrue(value['authenticated'])
        self.assertTrue(value['user']['emailVerified'])
        self.assertEqual(value['membership'], 'not_granted_by_sign_in')
        self.assertNotIn('access_token', response.body.decode())
        self.assertNotIn('id_token', response.body.decode())
        raw = self.service.database.read_bytes()
        self.assertNotIn(b'fixture@example.invalid', raw)
        self.assertNotIn(b'synthetic-access', raw)
        self.assertEqual(self.service.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(self.directory.name).stat().st_mode & 0o777, 0o700)

    def test_state_nonce_issuer_audience_pool_and_verified_email(self):
        for override in ({'nonce': 'wrong'}, {'iss': 'https://other.invalid'}, {'aud': 'other-client'},
                         {auth.ORG_CLAIM: 'other-pool'}, {'email_verified': False},
                         {'exp': self.now - 100}, {'email': ''}):
            with self.subTest(override=override):
                self.provider.overrides = override
                params, headers = self.login()
                response = self.callback(params, headers)
                self.assertEqual(response.status, 303)
                self.assertEqual(dict(response.headers)['Location'], '/account.html?auth=error')
                self.assertFalse(any(k == 'Set-Cookie' and v.startswith(auth.SESSION_COOKIE + '=')
                                     for k, v in response.headers))
        self.provider.overrides = {}
        params, headers = self.login()
        params['state'] = ['wrong']
        self.assertEqual(dict(self.callback(params, headers).headers)['Location'], '/account.html?auth=error')

    def test_callback_is_one_use_even_concurrently(self):
        parameters, headers = self.login()
        responses = []
        threads = [threading.Thread(target=lambda: responses.append(self.callback(parameters, headers))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(dict(r.headers)['Location'] for r in responses), ['/', '/account.html?auth=error'])
        self.assertEqual(self.provider.calls, 1)

    def test_missing_cookie_duplicate_query_and_callback_issuer(self):
        params, headers = self.login()
        self.assertEqual(dict(self.callback(params, self.headers).headers)['Location'], '/account.html?auth=error')
        duplicate = self.service.handle('GET', '/auth/callback?code=x&code=y&state=z', headers)
        self.assertEqual(dict(duplicate.headers)['Location'], '/account.html?auth=error')
        wrong_issuer = self.service.handle('GET', '/auth/callback?code=x&state=' + params['state'][0]
                                          + '&iss=https%3A%2F%2Fwrong.invalid', headers)
        self.assertEqual(dict(wrong_issuer.headers)['Location'], '/account.html?auth=error')

    def test_logout_requires_post_and_exact_origin_and_ends_provider_session(self):
        headers = self.authenticated()
        self.assertEqual(self.service.handle('GET', '/auth/logout', headers).status, 405)
        self.assertEqual(self.service.handle('POST', '/auth/logout', headers).status, 403)
        self.assertEqual(self.service.handle('POST', '/auth/logout', {**headers, 'Origin': 'https://evil.invalid'}).status, 403)
        response = self.service.handle('POST', '/auth/logout', {**headers, 'Origin': auth.ORIGIN})
        self.assertEqual(response.status, 303)
        location = urlsplit(dict(response.headers)['Location'])
        self.assertEqual(location.netloc, 'id.relcom.com')
        parameters = parse_qs(location.query)
        self.assertEqual(parameters['post_logout_redirect_uri'], ['https://ipvx.org/account.html'])
        self.assertIn('id_token_hint', parameters)
        self.assertFalse(json.loads(self.service.handle('GET', '/auth/session', headers).body)['authenticated'])

    def test_expiry_revocation_and_provider_outage(self):
        headers = self.authenticated()
        self.now += 601
        self.provider.unavailable = True
        self.assertEqual(self.service.handle('GET', '/auth/session', headers).status, 503)
        self.provider.unavailable = False
        self.provider.rejected = True
        self.assertFalse(json.loads(self.service.handle('GET', '/auth/session', headers).body)['authenticated'])
        self.provider.rejected = False
        headers = self.authenticated()
        self.now += 3601
        self.assertFalse(json.loads(self.service.handle('GET', '/auth/session', headers).body)['authenticated'])

    def test_untrusted_return_path_canonical_host_and_unknown_routes(self):
        for path in ('//evil.invalid', '/\\evil.invalid', '/\t/evil.invalid', 'https://evil.invalid'):
            self.assertEqual(auth._local_path(path), '/')
        self.assertEqual(self.service.handle('GET', '/auth/session', {'Host': 'www.ipvx.org'}).status, 400)
        self.assertIsNone(self.service.handle('GET', '/api/mesh', self.headers))
        self.assertIsNone(self.service.handle('GET', '/auth/unknown', self.headers))

    def test_changed_client_configuration_invalidates_saved_session(self):
        headers = self.authenticated()
        changed = auth.AuthService('different-client', 'pool-1', self.directory.name,
                                   provider=self.provider, clock=lambda: self.now)
        self.assertFalse(json.loads(changed.handle('GET', '/auth/session', headers).body)['authenticated'])

    def test_tampered_and_unsigned_tokens_refused(self):
        now = self.now
        claims = {'iss': auth.ISSUER, 'aud': 'client-1', 'sub': 'x', 'iat': now, 'exp': now + 60,
                  'nonce': 'n', auth.ORG_CLAIM: 'pool-1', 'email': 'x@example.invalid', 'email_verified': True}
        key = RSAKey.generate_key(2048, parameters={'kid': 'local-test'})
        bad = jwt.encode({'alg': 'RS256', 'kid': 'local-test'}, claims, key)
        with self.assertRaises(auth.AuthFailure):
            self.provider.validate_id_token(bad, 'n', 'a', now=now)
        encoded = secrets.token_urlsafe(30) + '.' + secrets.token_urlsafe(20) + '.'
        with self.assertRaises(auth.AuthFailure):
            self.provider.validate_id_token(encoded, 'n', 'a', now=now)

    def test_real_authlib_exchange_sends_public_pkce_contract(self):
        provider = auth.RelcomProvider('client-1', 'pool-1')
        provider._keys, provider._keys_at = self.provider.keys, time.time()
        now = int(time.time())
        claims = {'iss': auth.ISSUER, 'aud': 'client-1', 'sub': 'real-library-fixture',
                  'iat': now, 'exp': now + 3600, 'nonce': 'expected-nonce',
                  auth.ORG_CLAIM: 'pool-1', 'email': 'fixture@example.invalid', 'email_verified': True}
        encoded = jwt.encode({'alg': 'RS256', 'kid': 'local-test'}, claims, self.provider.key)
        captured = []
        def send(session, request, **kwargs):
            captured.append(request)
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps({'access_token': 'fixture-access', 'token_type': 'Bearer',
                                            'id_token': encoded, 'expires_in': 3600}).encode()
            response.request = request
            return response
        with patch('requests.sessions.Session.send', send):
            user, credentials, lifetime = provider.exchange('the-code', 'the-pkce-verifier', 'expected-nonce')
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].url, 'https://id.relcom.com/oauth/v2/token')
        body = parse_qs(captured[0].body)
        self.assertEqual(body['client_id'], ['client-1'])
        self.assertEqual(body['code_verifier'], ['the-pkce-verifier'])
        self.assertEqual(body['grant_type'], ['authorization_code'])
        self.assertEqual(body['redirect_uri'], ['https://ipvx.org/auth/callback'])
        self.assertNotIn('client_secret', body)
        self.assertEqual(user['sub'], 'real-library-fixture')
        self.assertEqual(lifetime, 3600)

    def test_concurrent_logout_cannot_be_undone_by_recheck(self):
        headers = self.authenticated()
        self.now += 601
        def recheck(credentials, user):
            result = self.service.handle('POST', '/auth/logout', {**headers, 'Origin': auth.ORIGIN})
            self.assertEqual(result.status, 303)
        self.provider.recheck = recheck
        response = self.service.handle('GET', '/auth/session', headers)
        self.assertFalse(json.loads(response.body)['authenticated'])
        self.assertFalse(json.loads(self.service.handle('GET', '/auth/session', headers).body)['authenticated'])

    def test_state_child_under_systemd_managed_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            private.mkdir(mode=0o700)
            managed = root / 'managed'
            managed.symlink_to(private, target_is_directory=True)
            # DynamicUser StateDirectory can be a trusted parent link. The
            # application's final state directory, key and database remain real files.
            service = auth.AuthService('client-1', 'pool-1', managed / 'state', provider=self.provider)
            self.assertEqual(service.handle('GET', '/auth/session', self.headers).status, 200)
            self.assertEqual((private / 'state').stat().st_mode & 0o777, 0o700)
            self.assertEqual((private / 'state/cookie.key').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                auth.AuthService('client-1', 'pool-1', managed, provider=self.provider)


if __name__ == '__main__':
    unittest.main()
