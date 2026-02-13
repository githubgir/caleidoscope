"""Collector registry - imports and registers all collector classes."""

from typing import Type

from caleidoscope.collectors.base import BaseCollector

# Registry mapping collector names to classes
ALL_COLLECTORS: dict[str, Type[BaseCollector]] = {}

# Import collectors with error handling
# Agent 2 will create these, so we use try/except to avoid ImportErrors

try:
    from caleidoscope.collectors.msci import MSCICollector

    ALL_COLLECTORS["msci"] = MSCICollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.sp_dji import SPDJICollector

    ALL_COLLECTORS["sp_dji"] = SPDJICollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.stoxx import STOXXCollector

    ALL_COLLECTORS["stoxx"] = STOXXCollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.blackrock import BlackRockCollector

    ALL_COLLECTORS["blackrock"] = BlackRockCollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.edgar import EDGARCollector

    ALL_COLLECTORS["edgar"] = EDGARCollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.google_news import GoogleNewsCollector

    ALL_COLLECTORS["google_news"] = GoogleNewsCollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.market_news import MarketNewsCollector

    ALL_COLLECTORS["market_news"] = MarketNewsCollector
except ImportError:
    pass

try:
    from caleidoscope.collectors.etf_news import ETFNewsCollector

    ALL_COLLECTORS["etf_news"] = ETFNewsCollector
except ImportError:
    pass
