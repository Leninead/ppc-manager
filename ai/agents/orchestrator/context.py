"""The app-wide chat agent. It has no analysis of its own, so it builds no payload.

Its documents are the analyses the pages share (core.app_chat), and ai.runtime
imports this module while loading every agent: it must not import core or ai.runtime.
"""
