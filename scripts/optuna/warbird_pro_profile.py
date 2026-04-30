#!/usr/bin/env python3
"""Warbird Pro Optuna profile.

This module is the active import path for the canonical
`indicators/warbird-pro-indicator.pine` surface. The implementation remains in
the former v7 profile module to preserve existing tests and helper imports while
the Pine surface is narrowed.
"""

from scripts.optuna.v7_warbird_institutional_profile import *  # noqa: F401,F403
