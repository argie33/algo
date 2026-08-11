"""Regression test for the 2026-08-11 fix: ParallelismValidator.validate_technical_data_loader()
imported from the non-existent `loaders.load_technical_data_daily` module (renamed to
`load_technical_indicators.py` at some point, but this import was never updated) - so this
check unconditionally failed with ModuleNotFoundError on every single call, always reporting
"Loader initialization failed" regardless of the loader's actual state.

Found by actually running utils.ops.production_readiness.ProductionReadinessCheck end-to-end -
a comprehensive readiness checker with 8 distinct checks that had never been invoked anywhere
outside its own test file (confirmed via repo-wide grep for `ProductionReadinessCheck(`), so
this stale import had never been exercised for real either.
"""

from utils.validation.parallelism import ParallelismValidator


class TestParallelismValidatorStaleModuleImport:
    def test_validate_technical_data_loader_imports_successfully(self):
        validator = ParallelismValidator()
        result = validator.validate_technical_data_loader()

        assert "error" not in result or "ModuleNotFoundError" not in str(result.get("error", "")), (
            f"validate_technical_data_loader() must not fail on import - got: {result}"
        )
        assert not any("Loader initialization failed" in issue for issue in result.get("issues_found", [])), (
            f"must not report a loader-init failure from the now-fixed import, got: {result}"
        )
