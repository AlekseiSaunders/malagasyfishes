"""Shared throttling for the submission write surface.

Architecture D10: one shared scope across both submission types closes the
``submit 10 husbandry + 10 population = 20 in an hour`` loophole.

The hourly scope is configured via DRF's ``DEFAULT_THROTTLE_RATES``; the
daily cap is enforced as a separate ``cache.incr`` counter in the view
(security must-have #3) because DRF only handles one scope per throttle
instance cleanly.
"""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class SubmissionsHourlyThrottle(UserRateThrottle):
    """10 submissions per user per hour across both submission types."""

    scope = "submissions_create"
