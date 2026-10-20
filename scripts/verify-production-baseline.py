#!/usr/bin/env python3
"""Read-only, fail-closed verification of Butterfly's saved Pages baseline.

Uses existing gh authentication/proxy configuration and normal HTTPS certificate
verification. No deployment, Git mutation, or environment configuration changes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASELINE = "ad8cda04dc84c70dbf3a4f1fbc12f711d4fd35bd"
REPOSITORY = "azizalbdah/butterfly-website"
DOMAIN = "butterflykwt.com"
PUBLIC_FILES = {
    "index.html": "/",
    "business.html": "/business.html",
    "catering.html": "/catering.html",
    "links.html": "/links.html",
    "assets/catering-configurator.js": "/assets/catering-configurator.js",
}


class EvidenceError(Exception):
    """Safe error text: never includes raw API responses or credential values."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class GitHubAPIError(EvidenceError):
    """Access failure, distinct from contradictory deployment evidence."""


class HTTPSOnlyRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        try:
            target = urlsplit(new_url)
            allowed = target.scheme == "https" and target.hostname == DOMAIN and target.port in (None, 443)
        except ValueError:
            allowed = False
        if not allowed:
            raise EvidenceError("Public redirect left the expected HTTPS custom domain.")
        return super().redirect_request(request, response, code, message, headers, new_url)


def github_json(endpoint: str):
    try:
        result = subprocess.run(
            ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json", endpoint],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitHubAPIError(f"GitHub API command unavailable ({type(exc).__name__}).") from None
    if result.returncode:
        match = re.search(r"HTTP (\d{3})", result.stderr)
        status = int(match.group(1)) if match else (403 if "Forbidden" in result.stderr else None)
        detail = f"HTTP {status}" if status else f"exit {result.returncode}"
        raise GitHubAPIError(f"GitHub API request failed ({detail}); check access and network policy.", status)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise GitHubAPIError("GitHub API returned invalid JSON.") from None


def fetch_https(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Butterfly-baseline-verifier", "Accept-Encoding": "identity"})
    try:
        # Default urllib HTTPS handling verifies certificates and preserves proxy settings.
        with build_opener(HTTPSOnlyRedirect()).open(request, timeout=20) as response:
            final = urlsplit(response.url)
            if final.scheme != "https" or final.hostname != DOMAIN or final.port not in (None, 443):
                raise EvidenceError("Public response redirected outside the expected HTTPS custom domain.")
            if response.status != 200:
                raise EvidenceError(f"Public response was HTTP {response.status}.")
            data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024:
                raise EvidenceError("Public response exceeded the verification size limit.")
            return data
    except HTTPError as exc:
        raise EvidenceError(f"Public HTTPS request failed (HTTP {exc.code}).", exc.code) from None
    except (URLError, OSError) as exc:
        raise EvidenceError(f"Public HTTPS request failed ({type(exc).__name__}); check TLS/network access.") from None


def read_git_file(root: Path, commit: str, filename: str) -> bytes:
    try:
        return subprocess.check_output(["git", "-C", str(root), "show", f"{commit}:{filename}"], stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        raise EvidenceError(f"Saved commit file unavailable: {filename}.") from None


def timestamp(value) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError("Deployment evidence has no valid timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed
    except ValueError:
        raise EvidenceError("Deployment evidence has no valid timestamp.") from None


def latest_active_pages_deployment(repository, api):
    """Find current successful github-pages deployment, never an older matching SHA.

    A newer failed deployment leaves an earlier successful deployment serving.
    Pending/unknown newer evidence blocks verification. Inactive deployments do
    not prove the currently deployed commit. The bounded query fails closed if
    no active success can be established in the latest 100 records.
    """
    base = f"repos/{repository}/deployments"
    deployments = api(base + "?environment=github-pages&per_page=100")
    if not isinstance(deployments, list):
        raise EvidenceError("Pages deployment list was not an array.")
    candidates = [d for d in deployments if isinstance(d, dict) and d.get("environment") == "github-pages"]
    if any(type(d.get("id")) is not int or d["id"] <= 0 for d in candidates):
        raise EvidenceError("Pages deployment has no valid identifier.")
    candidates.sort(key=lambda d: (timestamp(d.get("created_at")), d["id"]), reverse=True)
    for deployment in candidates:
        deployment_id = deployment.get("id")
        if not isinstance(deployment_id, int) or deployment_id <= 0:
            raise EvidenceError("Pages deployment has no valid identifier.")
        statuses = api(f"{base}/{deployment_id}/statuses?per_page=100")
        if not isinstance(statuses, list) or not statuses or not all(isinstance(s, dict) for s in statuses):
            raise EvidenceError("A newer Pages deployment has no usable status evidence.")
        status = max(statuses, key=lambda s: (timestamp(s.get("created_at")), s.get("id", 0)))
        state = status.get("state")
        if state in ("failure", "error", "inactive"):
            continue
        if state != "success":
            raise EvidenceError("A newer Pages deployment is pending or has an unknown state.")
        try:
            url = urlsplit(status.get("environment_url") or "")
        except (TypeError, ValueError):
            raise EvidenceError("Successful Pages deployment has no usable public environment URL.") from None
        if url.scheme != "https" or url.hostname != DOMAIN or url.username or url.password:
            raise EvidenceError("Successful Pages deployment does not identify the expected HTTPS custom domain.")
        return {
            "id": deployment_id,
            "sha": deployment.get("sha"),
            "environment": "github-pages",
            "created_at": deployment.get("created_at"),
            "status": state,
            "status_created_at": status.get("created_at"),
        }
    return None


def verify(root: Path, baseline=BASELINE, repository=REPOSITORY, *, api=github_json, fetch=fetch_https, git_file=read_git_file):
    report = {
        "verified": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "repository": repository,
        "expected_commit": baseline,
        "expected_custom_domain": DOMAIN,
        "settings": None,
        "build_evidence": None,
        "deployment_evidence": None,
        "public_files": [],
        "errors": [],
        "notes": [],
    }
    errors = report["errors"]
    try:
        cname = git_file(root, baseline, "CNAME").decode().strip()
        if cname.casefold().rstrip(".") != DOMAIN:
            raise EvidenceError("Saved baseline CNAME does not match the expected custom domain.")
    except (EvidenceError, UnicodeError) as exc:
        errors.append(str(exc) if isinstance(exc, EvidenceError) else "Saved CNAME is not valid UTF-8.")

    try:
        pages = api(f"repos/{repository}/pages")
        if not isinstance(pages, dict):
            raise EvidenceError("Pages settings response was not an object.")
        source = pages.get("source")
        report["settings"] = {
            "cname": pages.get("cname"),
            "build_type": pages.get("build_type"),
            "source": {"branch": source.get("branch"), "path": source.get("path")} if isinstance(source, dict) else None,
            "https_enforced": pages.get("https_enforced"),
            "public": pages.get("public"),
            "status": pages.get("status"),
        }
        if not isinstance(pages.get("cname"), str) or pages["cname"].casefold().rstrip(".") != DOMAIN:
            raise EvidenceError("Live Pages CNAME does not match the expected custom domain.")
        build_type = pages.get("build_type")
        if build_type not in ("legacy", "workflow"):
            raise EvidenceError("Pages build type is unknown; actual deployment cannot be established.")
        if type(pages.get("https_enforced")) is not bool:
            raise EvidenceError("Pages HTTPS-enforcement setting is unknown.")
        if build_type == "legacy" and (
            not isinstance(source, dict)
            or not isinstance(source.get("branch"), str)
            or not source["branch"].strip()
            or source.get("path") not in ("/", "/docs")
        ):
            raise EvidenceError("Legacy Pages source branch/path is unknown or unsupported.")
        build = None
        try:
            build = api(f"repos/{repository}/pages/builds/latest")
        except EvidenceError:
            if build_type == "legacy":
                raise
            report["notes"].append("Legacy Pages build endpoint unavailable; workflow deployment evidence is required instead.")

        if build_type == "legacy":
            if not isinstance(build, dict) or build.get("status") != "built":
                raise EvidenceError("Latest legacy Pages build is not successfully built.")
            if timestamp(build.get("updated_at")) < timestamp(build.get("created_at")):
                raise EvidenceError("Latest Pages build timestamps are inconsistent.")
            build_evidence = {
                "kind": "legacy_pages_build",
                "sha": build.get("commit"),
                "status": build.get("status"),
                "created_at": build.get("created_at"),
                "updated_at": build.get("updated_at"),
            }
            if type(build.get("id")) is int and build["id"] > 0:
                build_evidence["id"] = build["id"]
            if isinstance(build.get("url"), str):
                try:
                    api_url = urlsplit(build["url"])
                    if (api_url.scheme == "https" and api_url.hostname == "api.github.com"
                            and not api_url.username and not api_url.password and not api_url.query
                            and api_url.path.startswith(f"/repos/{repository}/pages/builds/")):
                        build_evidence["api_url"] = build["url"]
                except ValueError:
                    pass
            report["build_evidence"] = build_evidence
            report["deployment_evidence"] = dict(build_evidence)
            if build.get("commit") != baseline:
                raise EvidenceError("Latest successful Pages build commit differs from the saved baseline.")

        try:
            deployed = latest_active_pages_deployment(repository, api)
        except GitHubAPIError:
            if build_type == "workflow":
                raise
            # Legacy /pages/builds/latest is authoritative for branch-based Pages.
            report["notes"].append("Supplementary deployment statuses unavailable; legacy build evidence was used.")
            deployed = None
        if build_type == "workflow" and deployed is None:
            raise EvidenceError("No active successful github-pages deployment was established; older runs are insufficient.")
        if deployed:
            report["deployment_evidence"] = {"kind": "github_pages_deployment", **deployed}
            if deployed["sha"] != baseline:
                raise EvidenceError("Latest active successful Pages deployment commit differs from the saved baseline.")
    except EvidenceError as exc:
        errors.append(str(exc))

    for filename, public_path in PUBLIC_FILES.items():
        item = {"file": filename, "verified": False}
        try:
            expected = hashlib.sha256(git_file(root, baseline, filename)).hexdigest()
            actual = hashlib.sha256(fetch(f"https://{DOMAIN}{public_path}")).hexdigest()
            item.update({"expected_sha256": expected, "public_sha256": actual, "verified": expected == actual})
            if expected != actual:
                errors.append(f"Public file differs from saved baseline: {filename}.")
        except EvidenceError as exc:
            item["error"] = str(exc)
            errors.append(f"Cannot verify {filename}: {exc}")
        report["public_files"].append(item)
    report["verified"] = not errors and report["deployment_evidence"] is not None and all(f["verified"] for f in report["public_files"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE, help="Full expected commit SHA; defaults to the saved production baseline.")
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--output", type=Path, help="Write JSON evidence outside the checkout; default: stdout.")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.baseline):
        parser.error("--baseline must be a full lowercase 40-character commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("--repository must have owner/repository form")
    root = Path(__file__).resolve().parents[1]
    if args.output and args.output.resolve().is_relative_to(root):
        parser.error("--output must be outside the checkout")
    report = verify(root, args.baseline, args.repository)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.write_text(serialized, encoding="utf-8")
        except OSError:
            print("Could not write verification report outside the checkout.", file=sys.stderr)
            return 2
        print(f"Production baseline {'VERIFIED' if report['verified'] else 'UNVERIFIED'}; report saved to {args.output}.")
        for error in report["errors"]:
            print(error, file=sys.stderr)
    else:
        print(serialized, end="")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
