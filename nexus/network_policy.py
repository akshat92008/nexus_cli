"""Network Policy — blocks SSRF, private-range access, and dangerous redirects.

Validates URLs before any outbound HTTP request to prevent Server-Side
Request Forgery (SSRF) and network abuse through the agent's web tools.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkViolation:
    """A single network policy violation."""

    url: str
    reason: str
    category: str  # "private_range", "metadata", "loopback", "blocked_scheme", etc.


# Cloud metadata endpoints (AWS, GCP, Azure, DigitalOcean, Oracle, Alibaba)
_METADATA_IPS = frozenset(
    {
        "169.254.169.254",  # AWS / GCP / Azure / most clouds
        "100.100.100.200",  # Alibaba Cloud
        "192.0.0.192",  # Oracle Cloud
    }
)

_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata.azure.com",
        "metadata.oraclecloud.com",
    }
)

_BLOCKED_SCHEMES = frozenset(
    {
        "file",
        "ftp",
        "gopher",
        "data",
        "javascript",
        "vbscript",
        "jar",
        "netdoc",
        "mailto",
    }
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})

MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB default limit

_DANGEROUS_CONTENT_TYPES = frozenset(
    {
        "application/x-executable",
        "application/x-sharedlib",
        "application/x-mach-binary",
        "application/x-dosexec",
    }
)


class NetworkPolicy:
    """Validates URLs against SSRF and network-abuse rules.

    Usage::

        policy = NetworkPolicy()
        violation = policy.check_url("http://169.254.169.254/latest/meta-data/")
        if violation:
            raise ValueError(violation.reason)
    """

    def __init__(
        self,
        *,
        allow_localhost: bool = False,
        allow_private: bool = False,
        allowed_hosts: frozenset[str] | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ):
        self.allow_localhost = allow_localhost
        self.allow_private = allow_private
        self.allowed_hosts = allowed_hosts  # If set, only these hosts are allowed
        self.max_response_bytes = max_response_bytes

    def check_url(self, url: str) -> NetworkViolation | None:
        """Validate a URL before making a request.  Returns None if allowed."""
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            return NetworkViolation(url, "Malformed URL", "parse_error")

        # ── Scheme check ────────────────────────────────────────────────
        scheme = (parsed.scheme or "").lower()
        if scheme in _BLOCKED_SCHEMES:
            return NetworkViolation(url, f"Blocked scheme: {scheme}", "blocked_scheme")
        if scheme not in _ALLOWED_SCHEMES:
            return NetworkViolation(url, f"Unsupported scheme: {scheme}", "blocked_scheme")

        # ── Host check ──────────────────────────────────────────────────
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            return NetworkViolation(url, "Empty hostname", "empty_host")

        # Check metadata hosts
        if hostname in _METADATA_HOSTS:
            return NetworkViolation(
                url,
                f"Cloud metadata hostname blocked: {hostname}",
                "metadata",
            )

        # Resolve to IP and check address ranges
        violation = self._check_host_ip(url, hostname)
        if violation:
            return violation

        # Optional allowlist
        if self.allowed_hosts is not None and hostname not in self.allowed_hosts:
            return NetworkViolation(
                url,
                f"Host not in allowlist: {hostname}",
                "not_allowed",
            )

        return None

    def check_redirect(self, original_url: str, redirect_url: str) -> NetworkViolation | None:
        """Revalidate a redirect destination — redirects into blocked ranges are SSRF."""
        violation = self.check_url(redirect_url)
        if violation:
            return NetworkViolation(
                redirect_url,
                f"Redirect from {original_url} leads to blocked destination: {violation.reason}",
                f"redirect_{violation.category}",
            )
        return None

    def check_content_type(self, content_type: str) -> NetworkViolation | None:
        """Check if a response content type is safe."""
        ct = content_type.lower().split(";")[0].strip()
        if ct in _DANGEROUS_CONTENT_TYPES:
            return NetworkViolation(
                "",
                f"Dangerous content type: {ct}",
                "dangerous_content_type",
            )
        return None

    def _check_host_ip(self, url: str, hostname: str) -> NetworkViolation | None:
        """Resolve hostname and check the IP address against blocked ranges."""
        try:
            addr = ipaddress.ip_address(hostname)
        except ValueError:
            # It's a hostname, try DNS resolution
            try:
                infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _family, _, _, _, sockaddr in infos:
                    ip_str = sockaddr[0]
                    violation = self._check_ip(url, ip_str, hostname)
                    if violation:
                        return violation
                return None
            except (socket.gaierror, OSError):
                # Can't resolve — allow (it will fail at request time anyway)
                return None
        else:
            return self._check_ip(url, str(addr), hostname)

    def _check_ip(self, url: str, ip_str: str, hostname: str) -> NetworkViolation | None:
        """Check a single IP address against blocked ranges."""
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return None

        # Cloud metadata IPs
        if ip_str in _METADATA_IPS:
            return NetworkViolation(
                url,
                f"Cloud metadata IP blocked: {ip_str} (resolved from {hostname})",
                "metadata",
            )

        # Loopback (127.0.0.0/8, ::1)
        if addr.is_loopback and not self.allow_localhost:
            return NetworkViolation(
                url,
                f"Loopback address blocked: {ip_str} (resolved from {hostname})",
                "loopback",
            )

        # Private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
        if addr.is_private and not self.allow_private:
            return NetworkViolation(
                url,
                f"Private address blocked: {ip_str} (resolved from {hostname})",
                "private_range",
            )

        # Link-local (169.254.0.0/16, fe80::/10)
        if addr.is_link_local:
            return NetworkViolation(
                url,
                f"Link-local address blocked: {ip_str} (resolved from {hostname})",
                "link_local",
            )

        # Multicast
        if addr.is_multicast:
            return NetworkViolation(
                url,
                f"Multicast address blocked: {ip_str}",
                "multicast",
            )

        # Unspecified (0.0.0.0, ::)
        if addr == ipaddress.ip_address("0.0.0.0") or addr == ipaddress.ip_address("::"):
            return NetworkViolation(
                url,
                f"Unspecified address blocked: {ip_str}",
                "unspecified",
            )

        return None
