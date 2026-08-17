"""Helpers for reading a config entry's effective configuration."""


def resolve_entry_config(config_entry):
    """Return the entry's effective config, options overriding initial setup data.

    Initial setup writes to ``config_entry.data``; the options flow writes to
    ``config_entry.options``. An entry whose options were never saved has an
    empty options mapping, so the merge falls back to the setup values.
    """
    return {**config_entry.data, **(config_entry.options or {})}
