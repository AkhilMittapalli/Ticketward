"""Domain layer: frozen taxonomy, ports (protocols) and domain errors.

Layering rule (spec §7.1): ``domain`` imports nothing from infrastructure
(no FastAPI, SQLAlchemy, Redis or provider SDKs).
"""
