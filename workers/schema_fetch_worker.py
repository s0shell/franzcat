import ssl
import urllib3
import json

from PyQt6.QtCore import QThread, pyqtSignal

class SchemaFetchWorker(QThread):
    """
    Fetches a schema from Confluent Schema Registry in a background thread.

    Endpoint:  GET {base_url}/schemas/ids/{schema_id}
    Response:  {"schema": "<json-string>", "schemaType": "AVRO"}

    Signals
    -------
    result(str, str)  — (pretty_schema_json, subject_name_or_empty)
    error(str)        — human-readable error message
    """

    result  = pyqtSignal(str, str)   # pretty schema, schema type
    error   = pyqtSignal(str)

    def __init__(self, base_url: str, schema_id: int, tls_cfg: dict | None):
        super().__init__()
        self.base_url  = base_url.rstrip("/")
        self.schema_id = schema_id
        self.tls_cfg   = tls_cfg   # None → plain HTTP / no client cert

    def _build_requests_kwargs(self) -> dict:
        kwargs: dict = {"timeout": 10}

        if self.tls_cfg is None:
            return kwargs

        # Server verification
        if not self.tls_cfg.get("verify", True):
            kwargs["verify"] = False
        elif self.tls_cfg.get("ca_cert"):
            kwargs["verify"] = self.tls_cfg["ca_cert"]

        # Client certificate (mTLS)
        client_cert = self.tls_cfg.get("client_cert", "").strip()
        client_key  = self.tls_cfg.get("client_key",  "").strip()
        if client_cert and client_key:
            passphrase = self.tls_cfg.get("key_passphrase", "").strip() or None
            if passphrase:
                # requests doesn't support encrypted key files directly;
                # load via ssl.SSLContext and pass the context instead
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ca = self.tls_cfg.get("ca_cert", "").strip()
                if ca:
                    ctx.load_verify_locations(ca)
                else:
                    ctx.check_hostname = False
                    ctx.verify_mode    = ssl.CERT_NONE
                ctx.load_cert_chain(client_cert, client_key, passphrase)
                kwargs["verify"] = False   # SSLContext handles verification
                # Wrap via HTTPAdapter — stored for use by caller if needed
                self._ssl_context = ctx
            else:
                kwargs["cert"] = (client_cert, client_key)

        return kwargs

    def _build_http_client(self):
        """
        Returns a configured urllib3 PoolManager.
        """

        if self.tls_cfg is None:
            return urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=10.0, read=10.0)
            )

        verify = self.tls_cfg.get("verify", True)
        ca_cert = self.tls_cfg.get("ca_cert", "").strip()

        if verify:
            ctx = ssl.create_default_context()

            if ca_cert:
                ctx.load_verify_locations(cafile=ca_cert)
        else:
            ctx = ssl._create_unverified_context()

        client_cert = self.tls_cfg.get("client_cert", "").strip()
        client_key = self.tls_cfg.get("client_key", "").strip()

        if client_cert and client_key:
            ctx.load_cert_chain(
                certfile=client_cert,
                keyfile=client_key,
                password=self.tls_cfg.get("key_passphrase") or None,
            )

        return urllib3.PoolManager(
            ssl_context=ctx,
            timeout=urllib3.Timeout(connect=10.0, read=10.0),
        )

    def run(self):
        url = f"{self.base_url}/schemas/ids/{self.schema_id}"

        try:
            http = self._build_http_client()

            resp = http.request(
                "GET",
                url,
                headers={"Accept": "application/json"},
            )

        except ssl.SSLError as exc:
            self.error.emit(f"TLS error: {exc}")
            return

        except urllib3.exceptions.SSLError as exc:
            self.error.emit(f"TLS error: {exc}")
            return

        except urllib3.exceptions.ConnectTimeoutError:
            self.error.emit("connection timed out (10 s)")
            return

        except urllib3.exceptions.ReadTimeoutError:
            self.error.emit("request timed out (10 s)")
            return

        except urllib3.exceptions.MaxRetryError as exc:
            self.error.emit(f"connection error: {exc}")
            return

        except Exception as exc:
            self.error.emit(f"unexpected error: {exc}")
            return

        if resp.status == 401:
            self.error.emit(
                "HTTP 401 — unauthorized (check mTLS / credentials)"
            )
            return

        if resp.status == 403:
            self.error.emit("HTTP 403 — forbidden")
            return

        if resp.status == 404:
            self.error.emit(
                f"HTTP 404 — schema ID {self.schema_id} not found"
            )
            return

        if resp.status >= 400:
            self.error.emit(
                f"HTTP {resp.status}: "
                f"{resp.data.decode('utf-8', errors='replace')[:200]}"
            )
            return

        try:
            body = json.loads(
                resp.data.decode("utf-8")
            )
        except Exception:
            self.error.emit(
                f"invalid JSON in response: "
                f"{resp.data.decode('utf-8', errors='replace')[:200]}"
            )
            return

        raw_schema = body.get("schema", "")
        schema_type = body.get("schemaType", "AVRO")

        try:
            parsed = json.loads(raw_schema)
            pretty = json.dumps(parsed, indent=2)
        except (ValueError, TypeError):
            pretty = raw_schema

        self.result.emit(pretty, schema_type)