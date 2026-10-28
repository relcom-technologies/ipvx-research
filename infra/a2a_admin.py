"""Owner-session bridge to the fixed loopback intake; no visitor-supplied identity."""
from http.client import HTTPConnection, HTTPException
import json
import re
import secrets
import time
from a2a_store import admin_signature, canonical

class A2AAdmin:
    def __init__(self, key):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError('Private admin credential must contain 32 bytes')
        self.key = key

    def handle(self, method, path, actor, data=None):
        base = '/community/v1/agents/proposals'
        if method == 'GET' and re.fullmatch(re.escape(base) + r'(?:/page/[0-9]{1,4})?', path):
            target = '/internal/proposals' + path[len(base):]
            raw = b''
        elif method == 'POST' and re.fullmatch(re.escape(base) + r'/proposal_[a-f0-9]{24}/decision', path):
            if not isinstance(data, dict) or set(data) != {'decision','reason','requestId'}:
                return 400, {'error':'invalid_decision'}
            target = '/internal/proposals' + path[len(base):]
            raw = canonical({**data, 'actor':actor}).encode()
        else:
            return 404, {'error':'not_found'}
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        headers = {'Content-Type':'application/json', 'X-IPvX-Time':stamp,
                   'X-IPvX-Nonce':nonce,
                   'X-IPvX-Signature':admin_signature(self.key, method, target, raw, stamp, nonce)}
        conn = HTTPConnection('127.0.0.1', 8095, timeout=10)
        try:
            conn.request(method, target, body=raw, headers=headers)
            response = conn.getresponse()
            body = response.read(131073)
            if len(body) > 131072:
                raise ValueError('Response exceeds bound')
            return response.status, json.loads(body)
        except (OSError, ValueError, HTTPException):
            return 503, {'error':'agent_intake_temporarily_unavailable'}
        finally:
            conn.close()
