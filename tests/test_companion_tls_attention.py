"""Tests for companion TLS policy and attention notifications."""

from __future__ import annotations

import json
import ssl
import sys
import threading
import unittest
from http.client import HTTPSConnection
from unittest.mock import patch

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.companion import generate_pairing_token, start_companion
from runspecimen.companion_attention import notify_attention_requested, notify_mac
from runspecimen.companion_tls import (
    fingerprint_sha256_of_pem,
    generate_ephemeral_tls,
    host_requires_tls,
    normalize_fingerprint,
    peer_is_loopback,
    remote_confirm_transport_ok,
)
from runspecimen.errors import RunSpecimenError


class TestCompanionTLS(RunSpecimenTestCase):
    def test_host_requires_tls_policy(self) -> None:
        self.assertFalse(host_requires_tls("127.0.0.1"))
        self.assertFalse(host_requires_tls("localhost"))
        self.assertFalse(host_requires_tls("::1"))
        self.assertTrue(host_requires_tls("192.168.1.10"))
        self.assertTrue(host_requires_tls("100.64.1.2"))

    def test_remote_confirm_transport_gate(self) -> None:
        self.assertTrue(
            remote_confirm_transport_ok(client_address=("127.0.0.1", 1), connection=object())
        )
        self.assertFalse(
            remote_confirm_transport_ok(client_address=("192.168.1.20", 1), connection=object())
        )
        self.assertTrue(peer_is_loopback(("127.0.0.1", 9)))
        self.assertFalse(peer_is_loopback(("10.0.0.2", 9)))

    def test_ephemeral_tls_material_and_https_loopback(self) -> None:
        material = generate_ephemeral_tls(bind_host="127.0.0.1", destination=self.ws / "tls")
        self.assertTrue(material.cert_path.is_file())
        self.assertTrue(material.key_path.is_file())
        pem = material.cert_path.read_text(encoding="utf-8")
        self.assertEqual(fingerprint_sha256_of_pem(pem), material.fingerprint_sha256)
        self.assertEqual(
            normalize_fingerprint(material.fingerprint_sha256),
            material.fingerprint_sha256_compact,
        )

        contract_path = write_contract(self.ws, "contract.json", base_contract())
        token = generate_pairing_token()
        server, url, meta = start_companion(
            workspace=self.ws,
            contract_path=contract_path,
            pairing_token=token,
            host="127.0.0.1",
            port=0,
            tls_cert=material.cert_path,
            tls_key=material.key_path,
        )
        self.assertTrue(url.startswith("https://"))
        self.assertTrue(meta["tls"])
        self.assertEqual(meta["tls_fingerprint_sha256"], material.fingerprint_sha256)
        self.assertEqual(meta["ios_bundle_id"], "com.darashkevich.runspecimen.observe")
        self.assertEqual(meta["mac_companion_bundle_id"], "com.darashkevich.runspecimen.companion")
        self.assertIn("TestFlight", meta["shipping_channel"])

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = HTTPSConnection(host, port, context=ctx, timeout=5)
            conn.request("GET", "/v1/health")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(body["ok"])
            self.assertFalse(body["can_approve"])
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_non_loopback_without_openssl_fails_closed_when_forced(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        with patch("runspecimen.companion_tls.shutil.which", return_value=None):
            with self.assertRaises(RunSpecimenError):
                start_companion(
                    workspace=self.ws,
                    contract_path=contract_path,
                    pairing_token=generate_pairing_token(),
                    host="192.168.1.50",
                    allow_lan=True,
                )


class TestCompanionAttention(unittest.TestCase):
    def test_notify_mac_off_darwin_is_noop(self) -> None:
        with patch("runspecimen.companion_attention.sys.platform", "linux"):
            result = notify_mac(title="t", message="m", sound=True)
        self.assertFalse(result["delivered"])
        self.assertEqual(result["skipped"], "not-darwin")
        self.assertIn("Focus", result["focus_note"])

    def test_notify_attention_requests_sound_by_default(self) -> None:
        with patch("runspecimen.companion_attention.notify_mac") as mocked:
            mocked.return_value = {"ok": True, "delivered": True, "sound": True}
            notify_attention_requested(message="look")
            mocked.assert_called_once()
            kwargs = mocked.call_args.kwargs
            self.assertTrue(kwargs["sound"])
            self.assertIn("attention", kwargs["title"].lower())


if __name__ == "__main__":
    unittest.main()
