"""
Nexus Provider Architecture
"""

from nexus.providers.base import Provider
from nexus.providers.hosted import HostedProvider
from nexus.providers.nova import NovaProvider
from nexus.providers.router import FallbackRouter

__all__ = ["Provider", "HostedProvider", "NovaProvider", "FallbackRouter"]
