const express = require("express");

const { sendSuccess } = require("../utils/apiResponse");

const router = express.Router();

const DEFAULT_THRESHOLDS = {
  sahm_critical: 0.5,
  sahm_warning: 0.3,
  spread_critical: -0.5,
  spread_warning: 0,
  hy_spread_critical: 8,
  hy_spread_warning: 5,
  ig_spread_critical: 2.5,
  ig_spread_warning: 1.5,
  claims_critical: 30,
  claims_warning: 20,
  vix_critical: 35,
  vix_warning: 25,
  stress_critical: 1.5,
  stress_warning: 0.5,
  cfnai_critical: -0.7,
  cfnai_warning: -0.3,
};

router.get("/thresholds", (req, res) => {
  return sendSuccess(res, {
    thresholds: DEFAULT_THRESHOLDS,
  });
});

module.exports = router;
