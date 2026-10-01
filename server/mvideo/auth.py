import hashlib
import hmac
import secrets
import time


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, database):
        self.db = database
        # Tickets die on restart and are scoped to the originating session/resource.
        self.key = secrets.token_bytes(32)

    def pair_code(self):
        code = ''.join(secrets.choice('0123456789') for _ in range(8))
        with self.db.connect() as db:
            db.execute("INSERT OR REPLACE INTO pairing VALUES(1,?,?,0)", (digest(code), int(time.time())+300))
        return code

    def pair(self, code):
        with self.db.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM pairing WHERE id=1').fetchone()
            if not row or row['expires'] < time.time() or row['attempts'] >= 5:
                return None
            db.execute('UPDATE pairing SET attempts=attempts+1 WHERE id=1')
            if not hmac.compare_digest(row['hash'], digest(code)):
                return None
            db.execute('DELETE FROM pairing')
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?)', (digest(token), int(time.time()) + 90*86400))
            return token

    def valid_hash(self, hashed):
        with self.db.connect() as db:
            row = db.execute('SELECT expires FROM sessions WHERE hash=?', (hashed,)).fetchone()
        return bool(row and row[0] > time.time())

    def authenticate(self, token):
        hashed = digest(token)
        return hashed if self.valid_hash(hashed) else None

    def ticket(self, session, resource):
        expires = int(time.time())+4*3600
        payload = f'{session}.{expires}.{resource}'
        signature = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
        return f'{session}.{expires}.{signature}'

    def verify_ticket(self, ticket, resource):
        try:
            session, expiry, signature = ticket.split('.')
            payload = f'{session}.{expiry}.{resource}'
            expected = hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest()
            return int(expiry) > time.time() and hmac.compare_digest(signature,expected) and self.valid_hash(session)
        except (ValueError, TypeError):
            return False
