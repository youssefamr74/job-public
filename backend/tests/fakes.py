"""Fakes for the mail sources. No test talks to Google."""

from email.message import EmailMessage
from typing import Optional

from imapclient.exceptions import IMAPClientError, LoginError


def raw_email(subject: str, body: str, sender: str = "Northwind Labs <jobs@northwind.example>",
              date: str = "Mon, 15 Jan 2024 10:00:00 +0000", html: Optional[str] = None) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = date
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


class FakeImapMessage:
    def __init__(self, uid: int, msgid: int, thrid: int, raw: bytes, sent: bool = False):
        self.uid = uid
        self.msgid = msgid
        self.thrid = thrid
        self.raw = raw
        self.sent = sent


class FakeIMAPClient:
    """Enough of imapclient.IMAPClient for ImapSource."""

    def __init__(self, messages=None, uidvalidity: int = 1, password: str = "abcdabcdabcdabcd",
                 folder_name: str = "[Gmail]/Wszystkie", login_error: Optional[str] = None,
                 fail_fetch_uids: set[int] = frozenset()):
        self.messages = {m.uid: m for m in (messages or [])}
        self.uidvalidity = uidvalidity
        self.password = password
        self.folder_name = folder_name
        self.login_error = login_error
        self.fail_fetch_uids = set(fail_fetch_uids)
        self.searches: list = []
        self.logged_in_with: Optional[tuple] = None
        self.logged_out = False
        self.selected = False

    def login(self, user, password):
        if self.login_error:
            raise LoginError(self.login_error)
        if password != self.password:
            raise LoginError("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
        self.logged_in_with = (user, password)
        self.selected = False

    def list_folders(self):
        return [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
            ((b"\\HasNoChildren", b"\\Sent"), b"/", "[Gmail]/Sent Mail"),
            ((b"\\HasNoChildren", b"\\All"), b"/", self.folder_name),
        ]

    def select_folder(self, folder, readonly=False):
        assert folder == self.folder_name
        self.selected = True
        uidnext = max(self.messages, default=0) + 1
        return {b"UIDVALIDITY": self.uidvalidity, b"UIDNEXT": uidnext, b"EXISTS": len(self.messages)}

    def _not_sent(self):
        return [uid for uid, m in self.messages.items() if not m.sent]

    def gmail_search(self, query, charset="UTF-8"):
        self.searches.append(("X-GM-RAW", query))
        return sorted(self._not_sent())

    def search(self, criteria):
        if not self.selected:
            raise IMAPClientError("UID SEARCH not allowed now.")
        self.searches.append(tuple(criteria))
        if criteria[0] == "X-GM-MSGID":
            return [uid for uid, m in self.messages.items() if m.msgid == int(criteria[1])]
        assert criteria[0] == "UID" and criteria[2:] == ["X-GM-RAW", "-in:sent"]
        start = int(criteria[1].split(":")[0])
        matched = [uid for uid in self._not_sent() if uid >= start]
        newest = max(self.messages, default=None)
        if not matched and newest is not None and not self.messages[newest].sent:
            matched = [newest]
        return sorted(matched)

    def fetch(self, uids, items):
        out = {}
        for uid in uids:
            if uid not in self.messages:
                continue
            if uid in self.fail_fetch_uids and any(i.startswith("BODY") for i in items):
                raise OSError("connection reset")
            m = self.messages[uid]
            data = {b"SEQ": uid, b"X-GM-MSGID": m.msgid}
            if "X-GM-THRID" in items:
                data[b"X-GM-THRID"] = m.thrid
            if any(i.startswith("BODY") for i in items):
                data[b"BODY[]<0>"] = m.raw
            out[uid] = data
        return out

    def logout(self):
        self.logged_out = True


def api_message(message_id: str, thread_id: str, raw: bytes, label_ids=("INBOX",)) -> dict:
    """The Gmail API's format=full view of a raw email."""
    import base64
    import email
    import email.policy

    msg = email.message_from_bytes(raw, policy=email.policy.default)

    def part(p):
        if p.is_multipart():
            return {"mimeType": p.get_content_type(), "body": {"size": 0},
                    "parts": [part(child) for child in p.iter_parts()]}
        data = base64.urlsafe_b64encode(p.get_payload(decode=True) or b"").decode().rstrip("=")
        return {"mimeType": p.get_content_type(), "body": {"data": data}}

    payload = part(msg)
    payload["headers"] = [{"name": k, "value": str(v)} for k, v in msg.items()]
    return {"id": message_id, "threadId": thread_id, "labelIds": list(label_ids), "payload": payload}


class FakeGmailApi:
    """A tiny Gmail API and Google OAuth server for httpx.MockTransport."""

    def __init__(self, messages=(), history_id: int = 100, oldest_history_id: int = 0,
                 access_token: str = "good-token", page_size: int = 2):
        self.messages = {m["id"]: m for m in messages}
        self.order = [m["id"] for m in messages]
        self.history: list[dict] = []
        self.history_id = history_id
        self.oldest_history_id = oldest_history_id
        self.access_token = access_token
        self.page_size = page_size
        self.refresh_mode = "ok"
        self.issued = 0
        self.fail_ids: set[str] = set()
        self.revoked: list[str] = []
        self.requests: list[str] = []

    def add_history(self, record_id: int, *message_ids: str, labels=("INBOX",)) -> None:
        self.history.append({"id": str(record_id), "messagesAdded": [
            {"message": {"id": m, "labelIds": list(labels)}} for m in message_ids
        ]})
        self.history_id = max(self.history_id, record_id)

    def transport(self):
        import httpx
        return httpx.MockTransport(self.handle)

    def handle(self, request):
        import httpx
        from urllib.parse import parse_qs

        url = request.url
        self.requests.append(f"{request.method} {url.path}")
        if url.host == "oauth2.googleapis.com":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if url.path == "/revoke":
                self.revoked.append(form["token"])
                return httpx.Response(200)
            if form["grant_type"] == "refresh_token":
                if self.refresh_mode == "invalid_grant":
                    return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
                self.issued += 1
                self.access_token = f"token-{self.issued}"
                return httpx.Response(200, json={"access_token": self.access_token, "expires_in": 3599})
            if form.get("code") == "bad":
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.issued += 1
            self.access_token = f"token-{self.issued}"
            return httpx.Response(200, json={"access_token": self.access_token, "refresh_token": "refresh-1"})

        if request.headers.get("Authorization") != f"Bearer {self.access_token}":
            return httpx.Response(401, json={"error": {"code": 401}})
        path = url.path.replace("/gmail/v1/users/me", "")
        params = dict(url.params)
        if path == "/profile":
            return httpx.Response(200, json={"emailAddress": "me@gmail.com", "historyId": str(self.history_id)})
        if path == "/messages":
            ids = list(reversed(self.order))
            start = int(params.get("pageToken", 0))
            page = ids[start:start + min(self.page_size, int(params["maxResults"]))]
            body = {"messages": [{"id": m, "threadId": self.messages[m]["threadId"]} for m in page]}
            if start + len(page) < len(ids):
                body["nextPageToken"] = str(start + len(page))
            return httpx.Response(200, json=body)
        if path.startswith("/messages/"):
            message_id = path.split("/")[-1]
            if message_id in self.fail_ids:
                return httpx.Response(500)
            if message_id not in self.messages:
                return httpx.Response(404)
            return httpx.Response(200, json=self.messages[message_id])
        if path == "/history":
            start_id = int(params["startHistoryId"])
            if start_id < self.oldest_history_id:
                return httpx.Response(404)
            records = [r for r in self.history if int(r["id"]) > start_id]
            offset = int(params.get("pageToken", 0))
            page = records[offset:offset + self.page_size]
            body = {"history": page, "historyId": str(self.history_id)}
            if offset + len(page) < len(records):
                body["nextPageToken"] = str(offset + len(page))
            return httpx.Response(200, json=body)
        return httpx.Response(404)
