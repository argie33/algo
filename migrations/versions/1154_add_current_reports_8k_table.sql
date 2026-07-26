-- Migration 1154: Add SEC Form 8-K Current Reports table
-- Purpose: Track material events via SEC Form 8-K filings
-- These events are important for catalyst-based trading signals
-- Includes filing date, material items disclosed, and event descriptions

BEGIN;

-- Create current_reports_8k table for Form 8-K filings
CREATE TABLE IF NOT EXISTS current_reports_8k (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    filing_date DATE NOT NULL,
    accession_number VARCHAR(20) NOT NULL,
    form_type VARCHAR(10) NOT NULL DEFAULT '8-K',

    -- Material event classification
    item_1_01 BOOLEAN DEFAULT FALSE,  -- Bankruptcy or material loss
    item_1_02 BOOLEAN DEFAULT FALSE,  -- Unregistered sales
    item_1_03 BOOLEAN DEFAULT FALSE,  -- Bankruptcy proceedings
    item_2_01 BOOLEAN DEFAULT FALSE,  -- Completion of acquisition or disposition
    item_2_02 BOOLEAN DEFAULT FALSE,  -- Results of operations and financial condition
    item_2_03 BOOLEAN DEFAULT FALSE,  -- Creation of material direct financial obligation
    item_2_04 BOOLEAN DEFAULT FALSE,  -- Triggering of material definitive agreement
    item_2_05 BOOLEAN DEFAULT FALSE,  -- Costs associated with exit or disposal activities
    item_2_06 BOOLEAN DEFAULT FALSE,  -- Material impairments
    item_2_07 BOOLEAN DEFAULT FALSE,  -- Regulation FD disclosure
    item_2_08 BOOLEAN DEFAULT FALSE,  -- Other events
    item_3_01 BOOLEAN DEFAULT FALSE,  -- Default under material agreement
    item_3_02 BOOLEAN DEFAULT FALSE,  -- Unregistered sales of equity securities
    item_3_03 BOOLEAN DEFAULT FALSE,  -- Material modification of material agreement
    item_4_01 BOOLEAN DEFAULT FALSE,  -- Changes in registrant's certifying accountant
    item_4_02 BOOLEAN DEFAULT FALSE,  -- Non-reliance on financial statements
    item_5_01 BOOLEAN DEFAULT FALSE,  -- Costs associated with exit/disposal
    item_5_02 BOOLEAN DEFAULT FALSE,  -- Bankruptcy or receivership
    item_5_03 BOOLEAN DEFAULT FALSE,  -- Amendment to articles or bylaws
    item_5_05 BOOLEAN DEFAULT FALSE,  -- Amendments to articles of incorporation
    item_5_07 BOOLEAN DEFAULT FALSE,  -- Submission of matters to security holder vote
    item_6_01 BOOLEAN DEFAULT FALSE,  -- Bankruptcy or receivership
    item_7_01 BOOLEAN DEFAULT FALSE,  -- Regulation FD disclosure
    item_8_01 BOOLEAN DEFAULT FALSE,  -- Other events
    item_9_01 BOOLEAN DEFAULT FALSE,  -- Financial statements and exhibits

    -- Event summary and description
    event_summary TEXT,
    material_items_text TEXT,

    -- Data quality tracking
    data_unavailable BOOLEAN DEFAULT FALSE,
    data_unavailable_reason VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_8k_filing UNIQUE(symbol, accession_number),
    CONSTRAINT fk_8k_symbol FOREIGN KEY(symbol) REFERENCES stock_symbols(symbol) ON DELETE CASCADE
);

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_current_reports_8k_symbol_date ON current_reports_8k(symbol, filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_current_reports_8k_filing_date ON current_reports_8k(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_current_reports_8k_updated ON current_reports_8k(updated_at DESC);

-- Register in loader status tracking
INSERT INTO loader_status_registry (table_name, loader_name, is_critical, data_tier)
VALUES ('current_reports_8k', 'load_current_reports_8k', FALSE, 'AUXILIARY_COMPLETE')
ON CONFLICT (table_name) DO UPDATE SET
    loader_name = 'load_current_reports_8k',
    is_critical = FALSE,
    data_tier = 'AUXILIARY_COMPLETE';

COMMIT;
