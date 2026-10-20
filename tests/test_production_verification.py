"""Production evidence must fail closed, even if an older baseline once passed."""

import copy
import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "production_verification", Path(__file__).resolve().parents[1] / "scripts/verify-production-baseline.py"
)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class ProductionVerificationTests(unittest.TestCase):
    def setUp(self):
        self.base = "repos/azizalbdah/butterfly-website"
        self.pages = {
            "cname": verifier.DOMAIN,
            "build_type": "legacy",
            "source": {"branch": "main", "path": "/"},
            "https_enforced": True,
            "public": True,
            "status": "built",
        }
        self.build = {
            "status": "built", "commit": verifier.BASELINE,
            "created_at": "2026-10-19T10:00:00Z", "updated_at": "2026-10-19T10:01:00Z",
        }
        self.deployments = [self.deployment(20, verifier.BASELINE, "2026-10-19T10:00:00Z")]
        self.statuses = {20: [self.status("success", "2026-10-19T10:01:00Z")]}
        self.files = {filename: f"baseline {filename}".encode() for filename in verifier.PUBLIC_FILES}
        self.files["CNAME"] = (verifier.DOMAIN + "\n").encode()
        self.public = {f"https://{verifier.DOMAIN}{path}": self.files[filename] for filename, path in verifier.PUBLIC_FILES.items()}
        self.calls = []

    @staticmethod
    def deployment(deployment_id, sha, created_at):
        return {"id": deployment_id, "sha": sha, "environment": "github-pages", "created_at": created_at}

    @staticmethod
    def status(state, created_at):
        return {"state": state, "environment_url": f"https://{verifier.DOMAIN}/", "created_at": created_at, "id": 1}

    def api(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == self.base + "/pages":
            value = self.pages
        elif endpoint == self.base + "/pages/builds/latest":
            value = self.build
        elif endpoint == self.base + "/deployments?environment=github-pages&per_page=100":
            value = self.deployments
        else:
            deployment_id = int(endpoint.split("/deployments/")[1].split("/")[0])
            value = self.statuses[deployment_id]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def verify(self):
        return verifier.verify(
            Path("/unused"), api=self.api,
            fetch=lambda url: self.public[url],
            git_file=lambda _root, _sha, filename: self.files[filename],
        )

    def test_legacy_success_requires_deployment_and_public_file_agreement(self):
        report = self.verify()
        self.assertTrue(report["verified"], report["errors"])
        self.assertEqual(report["settings"]["source"], {"branch": "main", "path": "/"})
        self.assertEqual(report["deployment_evidence"]["sha"], verifier.BASELINE)
        self.assertEqual(len(report["public_files"]), 5)

    def test_workflow_success_uses_deployment_not_unsupported_legacy_endpoint(self):
        self.pages["build_type"] = "workflow"
        self.pages["source"] = None
        self.build = verifier.EvidenceError("HTTP 404", 404)
        self.assertTrue(self.verify()["verified"])

    def test_denied_settings_never_pass_with_matching_public_files(self):
        self.pages = verifier.EvidenceError("GitHub API request failed (HTTP 403).", 403)
        report = self.verify()
        self.assertFalse(report["verified"])
        self.assertIsNone(report["deployment_evidence"])
        self.assertIn("403", report["errors"][0])

    def test_public_mismatch_fails_even_with_successful_matching_deployment(self):
        self.public[f"https://{verifier.DOMAIN}/"] = b"new production HTML"
        report = self.verify()
        self.assertFalse(report["verified"])
        self.assertFalse(report["public_files"][0]["verified"])

    def test_newer_successful_commit_does_not_fall_back_to_old_matching_commit(self):
        self.pages["build_type"] = "workflow"
        self.deployments.append(self.deployment(21, "b" * 40, "2026-10-20T10:00:00Z"))
        self.statuses[21] = [self.status("success", "2026-10-20T10:01:00Z")]
        report = self.verify()
        self.assertFalse(report["verified"])
        self.assertEqual(report["deployment_evidence"]["sha"], "b" * 40)
        self.assertNotIn(self.base + "/deployments/20/statuses?per_page=100", self.calls)

    def test_pending_newer_deployment_blocks_readiness(self):
        self.pages["build_type"] = "workflow"
        self.deployments.append(self.deployment(21, verifier.BASELINE, "2026-10-20T10:00:00Z"))
        self.statuses[21] = [self.status("pending", "2026-10-20T10:01:00Z")]
        self.assertFalse(self.verify()["verified"])

    def test_pending_supplementary_deployment_also_blocks_legacy_readiness(self):
        self.deployments.append(self.deployment(21, verifier.BASELINE, "2026-10-20T10:00:00Z"))
        self.statuses[21] = [self.status("pending", "2026-10-20T10:01:00Z")]
        self.assertFalse(self.verify()["verified"])

    def test_failed_newer_deployment_leaves_earlier_success_active(self):
        self.pages["build_type"] = "workflow"
        self.deployments.append(self.deployment(21, "b" * 40, "2026-10-20T10:00:00Z"))
        self.statuses[21] = [self.status("failure", "2026-10-20T10:01:00Z")]
        report = self.verify()
        self.assertTrue(report["verified"], report["errors"])
        self.assertEqual(report["deployment_evidence"]["id"], 20)

    def test_inactive_old_deployment_is_not_current_success(self):
        self.pages["build_type"] = "workflow"
        self.statuses[20].append(self.status("inactive", "2026-10-20T10:01:00Z"))
        self.assertFalse(self.verify()["verified"])

    def test_missing_workflow_status_evidence_blocks_readiness(self):
        self.pages["build_type"] = "workflow"
        self.statuses[20] = []
        self.assertFalse(self.verify()["verified"])

    def test_wrong_live_custom_domain_fails(self):
        self.pages["cname"] = "wrong.example.com"
        self.assertFalse(self.verify()["verified"])

    def test_unknown_legacy_source_settings_fail(self):
        for source in (None, {}, {"branch": "", "path": "/"}, {"branch": "main", "path": None}):
            with self.subTest(source=source):
                self.pages["source"] = source
                self.assertFalse(self.verify()["verified"])

    def test_unknown_https_enforcement_fails_but_known_false_is_recorded(self):
        self.pages["https_enforced"] = None
        self.assertFalse(self.verify()["verified"])
        self.pages["https_enforced"] = False
        report = self.verify()
        self.assertTrue(report["verified"], report["errors"])
        self.assertIs(report["settings"]["https_enforced"], False)

    def test_invalid_or_missing_latest_build_timestamps_fail(self):
        for value in (None, "unknown", "2026-10-19T09:59:59Z"):
            with self.subTest(value=value):
                self.build["updated_at"] = value
                self.assertFalse(self.verify()["verified"])

    def test_build_metadata_retained_when_deployment_status_is_also_available(self):
        self.build["id"] = 123
        self.build["url"] = "https://api.github.com/" + self.base + "/pages/builds/123"
        report = self.verify()
        self.assertTrue(report["verified"], report["errors"])
        self.assertEqual(report["build_evidence"]["id"], 123)
        self.assertEqual(report["build_evidence"]["api_url"], self.build["url"])
        self.assertEqual(report["deployment_evidence"]["kind"], "github_pages_deployment")

    def test_failed_latest_legacy_build_never_passes_from_old_deployment(self):
        self.build["status"] = "errored"
        self.assertFalse(self.verify()["verified"])

    def test_newer_legacy_build_commit_mismatch_fails(self):
        self.build["commit"] = "b" * 40
        self.assertFalse(self.verify()["verified"])

    def test_legacy_build_is_authoritative_without_workflow_deployments(self):
        self.deployments = []
        report = self.verify()
        self.assertTrue(report["verified"], report["errors"])
        self.assertEqual(report["deployment_evidence"]["kind"], "legacy_pages_build")

    def test_https_failures_do_not_create_verified_results(self):
        def failing_fetch(_url):
            raise verifier.EvidenceError("Public HTTPS request failed (URLError); check TLS/network access.")
        report = verifier.verify(
            Path("/unused"), api=self.api, fetch=failing_fetch,
            git_file=lambda _root, _sha, filename: self.files[filename],
        )
        self.assertFalse(report["verified"])
        self.assertTrue(all(not item["verified"] for item in report["public_files"]))

    def test_https_redirect_cannot_downgrade_or_leave_custom_domain(self):
        handler = verifier.HTTPSOnlyRedirect()
        request = verifier.Request(f"https://{verifier.DOMAIN}/")
        for target in (f"http://{verifier.DOMAIN}/", "https://other.example/", f"https://{verifier.DOMAIN}:8443/"):
            with self.subTest(target=target), self.assertRaises(verifier.EvidenceError):
                handler.redirect_request(request, None, 301, "Moved", {}, target)


if __name__ == "__main__":
    unittest.main()
