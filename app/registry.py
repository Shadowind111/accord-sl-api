# -*- coding: utf-8 -*-
from __future__ import annotations

from app.plugins.base import RiskModelPlugin
from app.plugins.gist.plugin import GistPlugin
from app.plugins.referral_demo.plugin import ReferralDemoPlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, RiskModelPlugin] = {}
        for plugin in (GistPlugin(), ReferralDemoPlugin()):
            self._plugins[plugin.model_id] = plugin

    def get(self, model_id: str) -> RiskModelPlugin:
        if model_id not in self._plugins:
            raise KeyError(model_id)
        return self._plugins[model_id]

    def list(self) -> list[dict]:
        return [p.manifest for p in self._plugins.values()]


registry = PluginRegistry()
