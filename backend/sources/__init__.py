"""External data sources.

Each module wraps exactly one provider, returns plain dictionaries, and raises
`UpstreamError` with a message safe to show a user. Routers stay thin: they
choose what to expose, not how to parse someone else's payload.
"""
