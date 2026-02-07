import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Container, Box, Typography, Button, useTheme } from '@mui/material';
import { ArrowBack } from '@mui/icons-material';
import MarketingLayout from '../../components/marketing/MarketingLayout';
import CTASection from '../../components/marketing/CTASection';

const articlesData = [
  {
    id: 'great-rotation',
    title: 'The Great Rotation: Capital Flows Signal Structural Market Shift Away From Concentration',
    date: 'February 7, 2026',
    author: 'Erik A.',
    readTime: '12 min read',
    excerpt: 'Market breadth expanding significantly as institutional capital rotates away from mega-cap concentration. Analysis of flows, valuations, and structural drivers.',
    tags: ['Macro Analysis', 'Market Rotation', 'Institutional Flows', 'Valuation Reset'],
    tickers: [],
    content: `Our comprehensive analysis of market structure, institutional flows, and valuation dynamics reveals a secular shift in its early innings. After years where mega-cap technology stocks dominated returns and capital allocation, our data indicates a significant rotation is underway. Capital is now flowing broadly across market capitalization spectrum and into previously underperforming sectors.

The period from 2023 through 2025 produced one of the most concentrated bull markets in modern history. Seven mega-cap technology stocks represented 33% of S&P 500 market capitalization by January 2026. Forward P/E multiples on this concentrated group reached 28-35x, compared to 16x for the broader market. Valuation dispersion hit extremes not seen since the 1999 dot-com peak period.

This concentration created several mathematical realities that drive capital reallocation. The marginal utility problem is straightforward: $1 trillion in incremental capital flows faces a choice between adding to the $8 trillion "Magnificent Seven" market capitalization, or deploying to undervalued opportunities across 4,900 other tradeable companies. From an institutional ROI perspective, marginal returns are higher in areas with valuation disconnection.

As mega-cap stocks represent 33% of the S&P 500, adding to positions creates mechanical rebalancing issues. Equity funds with traditional 5-7% position limits in individual stocks hit ceilings, forcing capital elsewhere. Additionally, mega-cap technology earnings growth expectations declined from 20% plus in 2024 to 8-12% for 2026 forecasts. At 30x forward P/E, 10% growth doesn't support valuations. Markets are beginning to price this reality.

Concurrent with mega-cap tech valuation pressure, other market segments are showing valuation improvement. The mid-cap universe trades at 15-16x forward earnings with 1.3x book value, representing a 45-50% relative discount to mega-cap versus the historical average 20-25% discount. Small-cap equities trade at 13-14x forward earnings with a 55-60% valuation discount to mega-cap. Financials, industrials, and materials are experiencing valuation multiple expansion, while energy trades at 9-10x despite structural improvements in capital discipline.

Market breadth—the percentage of stocks trading above their 50-day moving average—provides the most reliable indicator of institutional participation quality. In 2022 during the bear market, breadth compressed to 8-12% for extended periods. During the 2023-2024 mega-cap rally, breadth averaged just 15-18%, suggesting weak participation. By January 2026, breadth was 18%, indicating exhaustion in mega-cap concentration. In February 2026 to date, breadth has expanded to 38%, the broadest participation in 10 years. This expansion is the critical signal that institutional capital is rotating rather than simply losing money.

Institutional flows confirm this rotation dynamic. Mega-cap technology funds are experiencing outflows for the first time since 2022, with Q1 2026 expected outflows of $8-12 billion from concentrated mega-cap tech vehicles. Mid-cap growth vehicles are experiencing inflows, with Q1 2026 projected inflows of $15-18 billion into mid-cap equity strategies, the highest quarterly inflow since 2021. Value factor funds show inflows after a 3-year drawdown period. Quality factor funds, which focus on consistent earnings and strong balance sheets, are showing sustained inflows. Momentum factor flows are shifting toward mid-cap and small-cap rather than mega-cap concentration.

International capital is also reallocating toward US equities. Non-US institutional investors are demonstrating increased US equity interest. European investors are trimming home-country overweights due to Eurozone slowing and geopolitical risks, increasing US equity allocation. Japanese institutional capital, historically home-biased, is showing increased US equity interest due to carry trade dynamics and relative valuation. Middle Eastern and sovereign wealth funds are discussing increased US equity commitment, reversing years of diversification away from concentration risk.

This rotation appears structural rather than cyclical. The breadth expansion from 18% to 38% in six weeks is the largest breadth expansion since 2016. When breadth is low with markets at highs, it signals concentration risk. When breadth expands from depressed levels while markets hold gains, it signals healthy rotation rather than correction. The magnitude and persistence of international capital flows typically involve 18-24 month rebalancing timelines as large portfolios gradually redeploy positions.

Policy environment tailwinds are supporting this rotation. The new administration's explicit pro-growth, pro-business agenda is removing barriers to AI adoption. Deregulation waves affecting financial services, healthcare, and energy are creating tailwinds for broader market participation. Companies in regulated sectors are suddenly having capital previously consumed by compliance now available for productivity investment. Tax policy discussions include potential corporate tax rate reductions and accelerated depreciation for AI and automation capex. Trade policy creates both opportunities and risks, with selective tariff implementation potentially creating "tariff winners" in domestic manufacturing.

The Great Rotation from concentrated mega-cap dominance to broad market participation represents a structural shift in capital allocation, not a temporary pullback. Institutional flows, valuation mathematics, policy environment tailwinds, and earnings expectations all support continuation of this rotation over the next 12-18 months. The expansion of market breadth from 18% to 38% in six weeks suggests institutional participation in widening leadership rather than retail chasing or short-covering.

Investors and advisors should position for rotation continuation while maintaining discipline around downside risks. Interest rate shocks above 4.5% would create headwinds for valuation expansion expectations. Earnings disappointment in Q1-Q2 2026 could trigger faster-than-expected sector reallocation back toward quality mega-cap. Geopolitical escalation could drive flight-to-quality back toward mega-cap concentrated leadership. Monetary policy errors where the Federal Reserve maintains tighter-than-appropriate policy longer than expected would constrain growth expectations broadly.

The probability-weighted scenario is continued breadth expansion through mid-2026, with valuation dispersion normalizing toward historical levels over the next 12-18 months. Sector diversification across rotation beneficiaries and risk management discipline prove more important than individual position selection during transitions this significant.`
  },
  {
    id: 'ai-efficiencies',
    title: 'The AI Productivity Inflection: How AI Adoption is Creating a Multi-Year Economic Super-Cycle',
    date: 'February 5, 2026',
    author: 'Erik A.',
    readTime: '14 min read',
    excerpt: 'AI benefits spreading from software into manufacturing, logistics, healthcare, and labor-intensive sectors creates structural GDP upside of 0.9-1.3% annually.',
    tags: ['AI Economics', 'Productivity', 'Structural Trends', 'Labor Economics'],
    tickers: [],
    content: `The narrative around artificial intelligence is fundamentally shifting. From 2023 through 2025, the dominant story positioned AI as a technology sector phenomenon—software capabilities that would benefit mega-cap technology companies. This narrative is becoming increasingly incomplete.

The real economic inflection point is AI spreading from software into manufacturing, logistics, healthcare, energy, and labor-intensive sectors. This represents a multi-year productivity super-cycle with potential to add 0.9-1.3% to annual GDP growth and generate 15-30% earnings growth for companies positioned in sectors with highest labor cost leverage. This is not a technology story. It's an economic productivity story.

Economists studying productivity cycles have noted a consistent pattern across transformative technologies: they don't generate immediate productivity gains. Instead, there's a lag period where the technology gets bolted onto existing infrastructure. During the electricity era from 1900-1910, electricity was installed in factories, but factories kept their old steam-powered physical layouts, resulting in minimal productivity improvements despite the revolutionary technology. From 1910-1920, as companies began reorganizing factories around electricity capabilities, productivity soared 3-5% annually. From 1920-1930, sustained productivity super-cycles emerged as electricity diffused through the entire economy.

AI is following this same pattern. From 2023-2024, the "bolt-on" AI phase occurred with ChatGPT and copilots added to existing software, resulting in tech companies capturing near-term revenue but minimal systemic efficiency gains. We are now in the "reorganization" phase from 2025-2026, where supply chains, manufacturing processes, and healthcare diagnostics are being redesigned around AI capabilities. Ahead lies the "super-cycle" phase from 2026-2028, where productivity gains compound across all sectors simultaneously, earnings surprise becomes normal rather than exception, and GDP growth re-rates higher on structural productivity gains.

Current consensus forecasts 2-2.3% GDP growth for 2026-2027, but this is materially too conservative if AI productivity adoption accelerates as expected. Let's quantify sector-by-sector impact. Manufacturing represents 14% of US GDP with current productivity growth of 1.2% annually. AI improvement potential reaches 1.5-2.0% annually through predictive maintenance reducing downtime 15-20%, quality control reducing scrap 4-8%, and supply chain optimization reducing inventory 12-18%. This creates a structural GDP impact of 0.2-0.28%.

Logistics and transportation represent 9% of US GDP with current productivity of 0.8% annually. AI improvement potential reaches 2.0-2.5% annually through route optimization saving fuel 12-15%, demand forecasting improving asset utilization 8-10%, and autonomous vehicle progression enabling safety improvements. This creates a structural GDP impact of 0.18-0.22%.

Healthcare delivery represents 18% of US GDP with current productivity of 0.3% annually (actually negative on quality-adjusted basis). AI improvement potential reaches 1.5-2.0% annually through diagnostic AI making imaging interpretation 40% faster, administrative automation making billing and coding 25% more efficient, and predictive care enabling preventive intervention reducing expensive acute care. This creates a structural GDP impact of 0.27-0.36%.

Financial services represent 8% of US GDP with current productivity of 1.0% annually and AI improvement potential of 1.8-2.2% annually through risk assessment automation, trading optimization, and regulatory compliance automation freeing analyst bandwidth for growth activities. Professional services represent 12% of US GDP with current productivity of 0.5% annually and AI improvement potential of 1.5-2.0% annually through document review and analysis acceleration, research acceleration, proposal generation, and quality control improvement.

The total potential structural GDP uplift reaches 0.9-1.29% annually. If these productivity gains materialize, 2026-2027 GDP growth could reach 2.9-3.6% versus current consensus 2.0-2.3%. This represents 1 percentage point of unexpected GDP growth, which typically translates to 8-12% earnings growth surprise when combined with margin expansion from productivity gains.

Sectors positioned to benefit most from AI adoption share specific characteristics. High labor cost burden, where labor constitutes 40% or more of operating costs, means AI productivity gains flow directly to bottom line. Inefficiency legacy, where historical constraints from safety regulations or technological limitations prevented optimization, creates opportunity as AI removes these constraints. Currently compressed margins, where companies run lean due to competitive pressure, mean cost structure improvement flows to profitability rather than being competed away. Recurring revenue models and sticky customer bases allow companies to maintain pricing power while improving margins.

Manufacturing and industrial sectors have labor representing 35-45% of costs. Capital equipment with 15-20 year replacement cycles means AI implementation doesn't require complete retooling. Compressed margins of 8-12% net mean productivity gains flow directly to earnings. Expected earnings beat potential reaches 15-25%.

Healthcare delivery has labor representing 50-60% of costs through nursing, technicians, and administrative staff. Regulatory environments create pricing constraints where companies can't easily raise prices. AI can reduce costs without reducing quality. Diagnostic accuracy actually improves with AI. Expected earnings beat potential reaches 20-30%.

Transportation and logistics have labor representing 40-50% of costs and fuel representing 20-25%, both addressable through AI optimization. Consolidation in the industry means productivity gains aren't immediately competed away. Asset-light models mean capex for AI implementation remains manageable. Expected earnings beat potential reaches 12-18%.

The energy sector, particularly upstream, has labor representing 25-35% of production costs. Safety constraints historically limited automation until AI safety monitoring made it viable. Capex spending is increasing due to policy tailwinds, creating capex efficiency opportunities. Commodity pricing provides earnings leverage on margin expansion. Expected earnings beat potential reaches 18-25%.

Q4 2025 earnings season in February-March 2026 represents critical validation. Companies have been deploying AI productivity improvements for 12-18 months. Q4 results should show margin expansion in labor-intensive industries, productivity gains flowing to bottom line, unexpected earnings beats in traditionally "boring" industrial names, and management commentary about AI implementation success. If this thesis is correct, we should see clusters of 10-15% earnings beats, with guidance expansion following.

Historical precedent demonstrates that when productivity cycles actually materialize, earnings surprises cluster for 3-6 consecutive quarters. We are positioned at the beginning of this cluster if the thesis proves correct. Interest rate risk remains a structural headwind. Current 10-year yield around 4.2% creates meaning headwind for capital allocation. Capex investment in automation requires 3-5 year payoff horizons, meaning projects need greater than 20% ROI to justify investment at current rates. Most industrial automation projects show 12-15% ROI, creating a gap.

Corporate debt at elevated levels creates constraint on earnings expansion. S&P 500 net debt-to-EBITDA stands at 2.1x historically elevated levels. Even with productivity gains, earnings expansion gets constrained by debt service requirements. Tariff policy execution risk presents both opportunity and threat. Measured tariffs create reshoring protection for domestic manufacturing, supporting capex investment. Broad, indiscriminate tariff implementation would create supply chain shock, stalling capex spending.

The transition from "bolt-on" AI implementation to "reorganization" around AI fundamentally shifts economic productivity potential. Historical precedent from electricity, computing, and other transformative technologies suggests a 3-5 year productivity super-cycle ahead. Earnings growth of 15-30% for well-positioned companies in labor-intensive, margin-constrained sectors is achievable over 18-24 months if productivity adoption accelerates as expected. The risk is not that productivity gains won't materialize. The risk is execution—policy disruption, rate shock, tariff dislocation, or earnings disappointment in early validation quarters could interrupt the cycle.

Structured, disciplined positioning in direct beneficiary sectors, combined with defensive hedges for risk scenarios, positions investors for participation in the productivity super-cycle while managing downside risks appropriately. Q4 2025 earnings season and Q1 2026 guidance will provide critical validation data. Within 90 days, we'll know whether this thesis is gaining traction or losing credibility.`
  }
];

const ArticleDetail = () => {
  const { articleId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();

  const article = articlesData.find(a => a.id === articleId);

  if (!article) {
    return (
      <MarketingLayout>
        <Container maxWidth="lg" sx={{ py: 8 }}>
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h4" sx={{ mb: 2 }}>Article not found</Typography>
            <Button onClick={() => navigate('/')} startIcon={<ArrowBack />}>
              Back to Home
            </Button>
          </Box>
        </Container>
      </MarketingLayout>
    );
  }

  return (
    <MarketingLayout>
      <Container maxWidth="md" sx={{ py: 6 }}>
        <Button
          onClick={() => navigate('/')}
          startIcon={<ArrowBack />}
          sx={{ mb: 4 }}
        >
          Back to Home
        </Button>

        {/* Article Header */}
        <Box sx={{ mb: 4 }}>
          <Typography
            variant="h2"
            sx={{
              fontSize: { xs: '2rem', md: '2.8rem' },
              fontWeight: 700,
              mb: 2,
              color: theme.palette.text.primary,
              lineHeight: 1.3,
            }}
          >
            {article.title}
          </Typography>

          <Box sx={{ display: 'flex', gap: 3, mb: 3, flexWrap: 'wrap' }}>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              <strong>Published:</strong> {article.date}
            </Typography>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              <strong>By:</strong> {article.author}
            </Typography>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              {article.readTime}
            </Typography>
          </Box>

          {/* Tags */}
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {article.tags.map((tag, i) => (
              <Typography
                key={i}
                sx={{
                  fontSize: '0.85rem',
                  backgroundColor: theme.palette.mode === 'dark'
                    ? 'rgba(33, 150, 243, 0.2)'
                    : 'rgba(33, 150, 243, 0.1)',
                  px: 1.5,
                  py: 0.5,
                  borderRadius: '4px',
                  color: theme.palette.primary.main,
                  fontWeight: 600,
                }}
              >
                {tag}
              </Typography>
            ))}
          </Box>
        </Box>

        {/* Article Content */}
        <Box
          sx={{
            '& p': {
              fontSize: '1.05rem',
              lineHeight: 1.9,
              color: theme.palette.text.secondary,
              mb: 2.5,
              '&:first-of-type': {
                fontSize: '1.15rem',
                fontWeight: 500,
                color: theme.palette.text.primary,
                mb: 3,
              },
            },
          }}
        >
          {article.content.split('\n\n').map((paragraph, idx) => {
            // Handle section headers
            if (paragraph.startsWith('##')) {
              const headerText = paragraph.replace(/^##\s/, '');
              return (
                <Typography
                  key={idx}
                  variant="h4"
                  sx={{
                    fontSize: '1.6rem',
                    fontWeight: 700,
                    mt: 4,
                    mb: 2,
                    color: theme.palette.text.primary,
                  }}
                >
                  {headerText}
                </Typography>
              );
            }

            // Skip empty paragraphs
            if (!paragraph.trim()) {
              return null;
            }

            // Regular paragraphs
            return (
              <Typography
                key={idx}
                sx={{
                  fontSize: '1.05rem',
                  lineHeight: 1.9,
                  color: theme.palette.text.secondary,
                  mb: 2.5,
                }}
              >
                {paragraph}
              </Typography>
            );
          })}
        </Box>

        <Box sx={{ mt: 6, pt: 4, borderTop: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
            This analysis represents comprehensive macro economic and market analysis. Suitable for institutional investors and advisors with multi-quarter to multi-year planning horizons.
          </Typography>
        </Box>
      </Container>

      <CTASection
        variant="dark"
        title="Ready to Access Professional Research?"
        subtitle="Get institutional-grade market research and advisory insights."
        primaryCTA={{ label: 'Launch Platform', link: '/app/market' }}
      />
    </MarketingLayout>
  );
};

export default ArticleDetail;
