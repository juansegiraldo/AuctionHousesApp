"""Bogota parser implementation (shared from legacy module)."""

from scraping.parsers import *  # noqa: F401,F403
# `import *` no re-exporta los nombres con `_`, y los tres runners los importan de aqui.
from scraping.parsers import _auction_id_from_url, _info_url_from_auction_url  # noqa: F401,E402
