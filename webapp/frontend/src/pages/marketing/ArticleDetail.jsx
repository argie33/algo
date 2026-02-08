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
    excerpt: 'Market breadth expanding significantly as institutional capital rotates away from mega-cap concentration.',
    tags: ['Macro Analysis', 'Market Rotation', 'Institutional Flows', 'Valuation Reset'],
    tickers: [],
    content: `The technology sector dominated market returns throughout 2024 and into early 2025, with the "Magnificent Seven" mega-cap stocks—Microsoft, Apple, Nvidia, Google, Amazon, Tesla, and Meta—driving a disproportionate share of S&P 500 returns. In 2024, these seven stocks accounted for approximately 30-33% of S&P 500 market capitalization and drove the majority of index gains, while the remaining 493 stocks in the index showed much more muted performance.

By December 2024, mega-cap technology stocks were trading at forward P/E multiples in the 25-35x range, compared to the S&P 500 average of approximately 18-19x. Nvidia, the semiconductor leader, was trading at forward multiples exceeding 40x on extremely high earnings growth expectations. The Federal Reserve held the effective federal funds rate at 5.25%-5.50% through September 2024, cut 25 basis points in November 2024, and cut another 25 basis points in December 2024, moving the rate to 4.25%-4.50% by year-end. This rate environment created mathematical pressure on high-multiple growth stocks, as the valuation multiples on technology stocks require extremely high earnings growth rates to justify prices when discount rates remain elevated.

Market structure during the 2024 mega-cap rally showed classic concentration dynamics. A small number of stocks drove index returns while broad market participation remained weak. Market breadth indicators—which measure the percentage of stocks participating in gains—remained depressed throughout much of 2024 despite the S&P 500 reaching all-time highs. This pattern is historically unsustainable and typically precedes periods of broader participation.

The driver of any rotation away from concentration is fundamentally mathematical. As mega-cap stocks become larger components of market indices and represent bigger portions of institutional portfolios, additional capital deployment becomes mechanically constrained. Position limit restrictions, index concentration limits, and basic valuation considerations create natural points where capital must flow elsewhere. This is not market inefficiency—it's mechanical necessity.

International capital allocation patterns shifted through 2024 and into 2025. The Japanese yen carry trade, which had been funding leveraged positions in higher-yielding assets, faced pressure from Bank of Japan rate increases and market volatility. This created forced rebalancing among international investors. Concurrently, US economic resilience relative to sluggish Eurozone growth made US equities increasingly attractive on a relative valuation basis for global investors.

The policy environment shifted meaningfully with the 2024 election cycle. The incoming administration's stated priorities emphasize deregulation, lower corporate tax rates, and infrastructure investment. Financial services, healthcare, and energy sectors stand to benefit most from reduced regulatory burden. These policy preferences would structurally favor smaller-capitalization and mid-capitalization companies over mega-cap technology, as regulatory compliance costs disproportionately affect smaller enterprises.

Artificial intelligence capabilities genuinely expanded significantly through 2024. Major technology companies deployed AI features across their platforms—Microsoft integrated Copilot more deeply into Office productivity tools, Google expanded AI search capabilities, and specialized applications of AI in data analysis, content creation, and business automation became more prevalent. However, the monetization of these capabilities remained uncertain, creating questions about whether valuation expansions were justified.

The debt environment remained a structural constraint on economic growth. US government debt exceeded $34 trillion by late 2024, with deficit spending remaining elevated. Corporate debt also reached elevated levels, with many companies carrying higher debt loads after the refinancing period of 2021-2023. This debt burden constrains both government spending flexibility and corporate capital allocation toward growth investment.

Earnings expectations moderated through 2024 compared to earlier optimistic forecasts. While technology sector earnings growth remained positive, the rate of growth expectations declined from the extreme levels priced in at some points during 2024. This moderation reflected both the practical challenges of AI monetization and the reality of slowing corporate earnings growth outside the technology sector.

The 2025 outlook included several key risks. Interest rates, while declining modestly, remained elevated by historical standards. Inflation remained above Federal Reserve targets, creating potential for rate pause or reversal if price pressures re-accelerated. Geopolitical tensions, particularly around Ukraine and potential Taiwan strait risks, created tail risks for markets. Trade policy uncertainty remained high given campaign rhetoric about tariff implementation.

Within this context, valuations across different market segments showed interesting divergence. Large-cap technology continued to command premium valuations, but mid-cap and smaller-cap equities appeared more attractively valued on traditional metrics. Sectors benefiting from economic growth but less dependent on technology disruption—financials, industrials, materials—offered reasonable value at reasonable prices. Healthcare, while historically expensive, showed moderating valuations.

Rotation dynamics, when they occur, typically reflect both valuation reset and performance-chasing. Early rotation participants move to value on valuation grounds. Later participants move based on relative performance—when cheaper areas outperform, additional capital follows. The historical pattern suggests that once rotation begins, breadth expansion and leadership change typically persist for multiple quarters before stabilizing at a new equilibrium.

Investors positioning for market transitions should focus on structural factors that support particular sectors. Deregulation benefits financial services and healthcare. Infrastructure investment benefits industrial and materials sectors. AI implementation in non-software contexts—logistics optimization, manufacturing automation, healthcare diagnostics—creates genuine productivity benefits in labor-intensive industries. These structural shifts support rotation scenarios independent of market sentiment.

Risk management during rotation periods emphasizes diversification and discipline. Interest rate movements remain the primary macro variable affecting valuation expectations. Earnings growth—or disappointment—will determine whether relative valuations can justify performance changes. Geopolitical events create sudden reversals. Maintaining balanced positioning rather than concentrating in rotation beneficiaries protects against scenario changes.`
  },
  {
    id: 'ai-efficiencies',
    title: 'The AI Productivity Inflection: How AI Adoption is Creating a Multi-Year Economic Super-Cycle',
    date: 'February 5, 2026',
    author: 'Erik A.',
    readTime: '14 min read',
    excerpt: 'AI benefits spreading from software into manufacturing, logistics, healthcare sectors.',
    tags: ['AI Economics', 'Productivity', 'Structural Trends', 'Labor Economics'],
    tickers: [],
    content: `The narrative around artificial intelligence shifted fundamentally through 2024 and into early 2025. From 2023 through mid-2024, the dominant story positioned AI as a technology sector phenomenon—advanced models and software capabilities that would primarily benefit mega-cap technology companies. By late 2024, the conversation was increasingly shifting toward practical implementation of AI across industries.

The real inflection point for economic impact comes from AI implementation spreading from software into manufacturing, logistics, healthcare, finance, and labor-intensive sectors. These sectors represent different economic dynamics than technology. Productivity in manufacturing increased 1.2% annually from 2015-2024. Productivity in transportation and warehousing increased 1.1% annually in the same period. Productivity in healthcare information systems has been constrained by regulatory complexity and legacy system requirements. These are sectors where meaningful productivity improvements have been elusive for decades.

The historical pattern of transformative technologies is well-documented. Electricity was invented in the 1880s, but broad productivity improvements didn't emerge until the 1920s and 1930s. The reason: early electricity implementations simply replaced steam engines while keeping the same factory layouts and processes. Only after companies restructured production processes around electricity—moving from centralized power to distributed electrical motors, redesigning floor layouts for efficiency—did productivity actually increase. This lag between capability development and productivity implementation typically spans 15-20 years.

Computer technology shows similar patterns. Computers were deployed in businesses starting in the 1960s and 1970s, but aggregate productivity growth actually slowed in the 1970s and 1980s despite massive computer investments. Productivity improvements only became visible in the 1990s and 2000s, after 20-30 years, when businesses had restructured operations around technology. This is known as the Solow Paradox—the gap between technological capability and measurable economic productivity.

AI is following this same technological adoption pattern. From 2023-2024, the "bolt-on" AI phase occurred with ChatGPT, Claude, and other generative AI tools added to existing software platforms and enterprise systems. Technology companies captured near-term revenue from API access and enterprise subscriptions, but systemic efficiency gains remained limited. We are entering the "reorganization" phase in 2025-2026, where organizations are beginning to restructure workflows, business processes, and job functions around AI capabilities.

Real productivity data reveals where AI impact may be significant. US labor productivity in 2024 grew at approximately 2.5% annually—above the 10-year average of 1.4% but still modest compared to historical periods. Within this, manufacturing productivity has been relatively flat around 1.2% growth annually since 2015. Healthcare productivity has been essentially flat or negative when quality-adjusted, because productivity improvements in administrative systems have been offset by regulatory complexity and legacy system constraints. Logistics and warehousing have seen productivity growth around 1.1% annually, constrained by labor costs and logistics complexity.

These sectors represent genuine productivity constraints. In healthcare, administrative costs represent 25-30% of total spending due to billing complexity, regulatory compliance, and fragmented IT systems. In logistics, fuel costs and driver labor represent 50-60% of operating costs, with little productivity improvement despite decades of "just-in-time" implementation. In manufacturing, quality control, inspection, and rework represent 5-8% of operating costs due to manual processes. These are measurable inefficiencies with quantified costs.

Manufacturing represents approximately 11% of US GDP based on recent Bureau of Economic Analysis data. Logistics and transportation represent approximately 3% of GDP directly, with additional impact through business operations. Healthcare represents approximately 17% of GDP. Financial services represent approximately 8% of GDP. These sectors represent roughly 40% of US GDP combined—sectors where productivity has been constrained.

AI capabilities deployed in these sectors show measurable early results. Computer vision systems in manufacturing quality control have achieved accuracy rates of 99%+ versus 97-98% for human inspection, at lower cost. Logistics optimization algorithms have achieved 5-8% fuel savings in real pilot programs. Healthcare diagnostic AI in specific applications (chest X-ray interpretation, pathology image analysis) has matched or exceeded human radiologist accuracy in peer-reviewed studies. These are not theoretical—they are deployed and measured.

Labor costs in key sectors are substantial and measurable. US manufacturing labor costs represent approximately 35-40% of operating costs across the sector. Freight and logistics industries have labor costs of 35-45% of operating costs (primarily driver wages and warehouse staffing). Hospital and healthcare provider labor costs represent 50-65% of operating expenses, the single largest cost category. These are not speculative—they are documented in industry financial reports and Bureau of Labor Statistics data.

Constraints preventing productivity improvements in these sectors are real and documented. Manufacturing faced automation constraints because upfront capital costs for robotics were high relative to benefit, and flexibility requirements favored human workers. Healthcare faced IT system fragmentation—hospitals typically operate multiple incompatible legacy systems from different vendors, making coordinated automation extremely difficult. Logistics faced labor scarcity in key regions and unpredictable demand patterns that made heavy automation economically marginal.

AI changes the economic equation in each sector differently. In manufacturing, computer vision quality control costs 30-50% less than human inspection with higher accuracy. In healthcare, administrative automation through natural language processing and document processing can reduce billing/coding labor requirements by 20-30% based on early implementations. In logistics, route optimization and demand prediction reduce fuel consumption and can reduce delivery time by 5-10% without labor displacement.

Federal policy environment matters for adoption speed. Tax incentives for capital investment would accelerate implementation. In 2024, depreciation rules and R&D tax credits remained in place, but proposals for accelerated depreciation on automation equipment would improve ROI on AI implementation projects. Reduced regulatory burden—which the incoming administration has emphasized—particularly matters for healthcare and financial services, where compliance costs currently consume significant resources that could otherwise fund productivity investment.

The labor market constraint is also real. The US unemployment rate in December 2024 was 4.2%, up from 3.7% in mid-2024 but historically still relatively low. Wage pressure remains present in labor-intensive sectors due to persistent labor shortages in nursing, warehouse work, and logistics roles. This creates genuine economic incentive to implement automation rather than compete for scarce labor at escalating wages.

The transition from "bolt-on" AI implementation to "reorganization" around AI fundamentally shifts economic productivity potential. Historical precedent from electricity, computing, and other transformative technologies suggests a 3-5 year productivity super-cycle ahead. The risk is not that productivity gains won't materialize. The risk is execution—policy disruption, rate shock, or earnings disappointment in early validation quarters could interrupt the cycle.

Structured, disciplined analysis of sector-specific productivity opportunities, combined with understanding of real constraints and real data, positions investors for participation in the emerging productivity cycle while managing downside risks appropriately.`
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
