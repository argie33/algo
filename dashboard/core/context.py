"""Dashboard context and data extraction."""

from typing import Any


class PanelDataExtractor:
    """Safely extracts panel data from dashboard result dict."""

    @staticmethod
    def safe_extract_items(raw_data: Any) -> list[Any] | dict[str, Any]:
        """Safely extract items, catching exceptions and converting to error dicts."""
        from dashboard.panels import _extract_items

        try:
            return _extract_items(raw_data)
        except (ValueError, TypeError) as e:
            return {"_error": f"Failed to extract items: {e}"}


class DashboardContext:
    """Context container for dashboard rendering with panel data."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Initialize context from orchestrator result."""
        self.data = data
        self._extractor = PanelDataExtractor()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def extract_items(self, raw_data: Any) -> list[Any] | dict[str, Any]:
        """Safely extract items from data."""
        return self._extractor.safe_extract_items(raw_data)

    @property
    def run(self) -> Any:
        return self.data.get("run")

    @property
    def cfg(self) -> Any:
        return self.data.get("cfg")

    @property
    def mkt(self) -> Any:
        return self.data.get("mkt")

    @property
    def port(self) -> Any:
        return self.data.get("port")

    @property
    def perf(self) -> Any:
        return self.data.get("perf")

    @property
    def pos(self) -> Any:
        return self.data.get("pos")

    @property
    def sig(self) -> Any:
        return self.data.get("sig")

    @property
    def health(self) -> Any:
        return self.data.get("health")

    @property
    def cb(self) -> Any:
        return self.data.get("cb")

    @property
    def trades(self) -> Any:
        return self.data.get("trades")

    @property
    def srank(self) -> Any:
        return self.extract_items(self.data.get("srank"))

    @property
    def activity(self) -> Any:
        return self.data.get("activity")

    @property
    def exp_factors(self) -> Any:
        return self.data.get("exp_factors")

    @property
    def eco(self) -> Any:
        return self.data.get("eco")

    @property
    def notifs(self) -> Any:
        return self.data.get("notifs")

    @property
    def sentiment(self) -> Any:
        return self.data.get("sentiment")

    @property
    def econ_cal(self) -> Any:
        return self.extract_items(self.data.get("econ_cal"))

    @property
    def risk(self) -> Any:
        return self.data.get("risk")

    @property
    def perf_anl(self) -> Any:
        return self.data.get("perf_anl")

    @property
    def sig_eval(self) -> Any:
        return self.data.get("sig_eval")

    @property
    def sec_rot(self) -> Any:
        return self.data.get("sec_rot")

    @property
    def algo_metrics(self) -> Any:
        return self.extract_items(self.data.get("algo_metrics"))

    @property
    def irank(self) -> Any:
        return self.extract_items(self.data.get("irank"))

    @property
    def audit(self) -> Any:
        return self.extract_items(self.data.get("audit"))

    @property
    def exec_hist(self) -> Any:
        return self.extract_items(self.data.get("exec_hist"))

    @property
    def scores(self) -> Any:
        return self.data.get("scores")
