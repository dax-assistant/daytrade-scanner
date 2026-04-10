# Ross Cameron / Warrior Trading — Day Trading Methodology

> Comprehensive reference document compiled from 4 Ross Cameron (Warrior Trading) YouTube video transcripts. Use this to verify scanner implementation against the actual strategy.

---

## 1. Philosophy & Mindset

### Small Account Challenge Approach
- Ross funded his first well-known challenge account with **$583.15** and grew it to **$100,000 in 45 days**
- By December of that year: **$335,000**; next year: ~$500,000; following year: crossed **$1 million**; pandemic year: crossed **$10 million**
- All profits subjected to **independent third-party accountant's audit**
- Current verified total (as of transcript recording): **$12.3–15.8 million** in audited profits
- He has done "more small account challenges than I can count" — routinely resets to $500–$2,000

### Proof of Concept in Simulator
- **Mandatory**: Practice strategy in a stock market simulator before risking real money
- "If you can't make money in a sim, you've got no business putting real money on the line"
- Sim trading removes emotional stakes, allowing focus on building skill
- Acceptable alternative: fund a real account with a small amount and trade with **1 share** (equivalent to sim trading)
- Minimum sim period: **10 days (2 trading weeks)** — what he calls "Trader Rehab"

### Discipline
- "I will share my strategy with you… but success will only come from traders who have the discipline to follow the rules"
- Two main causes of failure: (1) no strategy, (2) having a strategy but lacking discipline to follow it
- Even Ross himself occasionally breaks his own rules due to emotion

### Emotional Conditioning
- Separate emotions from trading by using a **trading plan** — losses become expected outcomes of a proven system, not personal failures
- Build **emotional intelligence and awareness** — journal reactions, put words to feelings
- Trade at the "edge of your comfort zone" for maximum growth
- If emotionally compromised: **stop trading immediately**
- Upload/review red day recaps alongside green days — normalize losses as part of the process

### Positive Feedback Loop
1. Focus on **A-quality setups** → increases accuracy
2. Higher accuracy → improves profit-to-loss ratio (eliminates outlier losses)
3. Better P/L ratio → more consistency (more green days/weeks)
4. Consistency → stronger track record
5. Strong track record → increased self-confidence
6. Confidence → increased share size and trade frequency
7. Larger size → increased profitability → **positive spiral**

### Negative Feedback Loop (Death Spiral)
1. Loss creates **strong emotion** (sadness, anger, frustration)
2. Desire to eliminate emotion → take another trade to "make it back"
3. Without strategy/discipline → more losses
4. More losses → more emotion → more desperate trades → **account blown**

### Breaking the Negative Spiral ("Trader Rehab")
- Reduce share size to a level that **does not trigger emotional response** (1 share, 10 shares, or simulator)
- Maintain for minimum **10 consecutive trading days**
- Focus purely on accuracy and quality setups
- Reset emotional baseline, then rebuild via positive feedback loop

---

## 2. Stock Selection — The 5 Pillars

These are the **critical scanner criteria**. All 5 must be met for an **A-quality setup**. A B-quality setup meets all except one (acceptable but higher risk; during small account challenges, Ross sticks primarily to A-quality).

### Pillar 1: Minimum % Up on Day
- Stock must be **up at least 10%** on the day
- Rationale: Out of ~10,000 stocks in the market, only ~100 are up >10% on any given day — this instantly filters to relevant candidates
- Ross's own data confirms he makes "far more money when the stock is up at least 10%"

### Pillar 2: Price Range
- **$2 to $20** — this is where outsized profits occur
- **Sweet spot: $3 to $8** (for small account challenge) or **$5 to $10** (general trading)
- Lower-priced stocks produce larger percentage moves ($2→$4 = 100%; $400→$800 virtually never happens)
- 95% of top 100 daily gainers are under $30
- Ross has made money below $2 and above $20, but the vast majority of profit is in the $2–$20 range

### Pillar 3: Relative Volume
- Must have **at least 5× relative volume** (compared to 50-day average daily volume)
- In practice, leading gainers often have relative volume of **80× to 2,500×**
- High relative volume signals "something special is happening today" — breaking news
- Important distinction: **high total volume alone is not sufficient** — it must be high *relative* to the stock's normal volume
- A large-cap stock with 155M shares of daily volume but only 1.2× relative volume is NOT a candidate

### Pillar 4: Float (Supply)
- **Maximum 20 million shares** (cannot be above this)
- **Under 10 million preferred**; under 5 million even better; **under 2 million = ideal** for small account challenges
- Float = number of shares available to trade on the open market
- Low float creates the supply/demand imbalance that drives 100%+ moves
- Top 10 leading gainers almost always have floats under 10 million shares
- Example from transcript: 930,000 share float with 58M volume = 58:1 demand/supply ratio

### Pillar 5: News Catalyst
- Stock must have **breaking news** driving the move
- This is the one pillar that occasionally won't be present (short squeeze, sector sympathy) — but trading without it is higher risk
- The catalyst is what creates the demand (volume)

#### Catalyst Types (ranked by impact):
1. **Clinical trial results** (biotech/pharma) — "probably one of the biggest ones"
2. **FDA approvals** — significant but often preceded by clinical trial move
3. **Earnings surprises** — especially steep revenue increases on small-cap companies
4. **New contracts / partnerships** — e.g., SpaceX satellite launch partnership
5. **Sector-specific news** — drones, AI, quantum computing, crypto, pandemic-related

#### Multiplying Factors:
- **Trending sector keywords** in the headline (AI, crypto, Bitcoin, COVID, quantum, etc.) — can cause outsized moves even if tangential
- **Recent IPO** — newer companies can produce exponentially bigger percentage gains
- **Recent SPAC (Special Acquisition Company)**
- **Recent reverse split**
- **Hot sector alignment** — pharmaceutical, Chinese stocks, AI companies
- Beware of "keyword stuffing" in headlines (companies strategically using trending terms for attention)

### Supply & Demand Relationship
The core principle: **bigger imbalance between supply (float) and demand (volume) = bigger percentage move**

| Float | Volume | Expected % Change |
|-------|--------|-------------------|
| 4M shares | 80M shares | ~115% |
| 4M shares | 160M shares | ~230% |
| 8M shares | 80M shares | ~60% |
| 2M shares | 80M shares | potentially 200%+ |

---

## 3. Scanner Criteria

### What to Program
The scanner searches the **entire market in real time** for stocks meeting these criteria:
1. **Up at least 10%** on the day (percentage change filter)
2. **Price between $2 and $20**
3. **Relative volume ≥ 5×** (vs. 50-day average)
4. **Float ≤ 20 million shares** (ideally under 10M)
5. **Breaking news present** (flagged with a flame/news icon)

### Sorting & Prioritization
- Primary sort: **total percentage gain** (leading percentage gainer = most attention)
- Secondary checks: float (sort low→high to find best supply/demand imbalance), relative volume, total volume
- The **#1 leading percentage gainer** in the market gets the most attention from all brokers pushing alerts, media coverage, and retail trader FOMO — this creates a self-reinforcing volume cycle

### Timing
- Scanners run from **7:00 AM to 10:00 AM Eastern** (primary trading window)
- Scanners technically continue running all day, but Ross only actively uses them 7–10 AM
- Ross sits down at **6:45 AM** to review pre-market data
- Audio alerts notify him in real time when a stock hits scanner criteria

### How He Reads Scanner Alerts
1. Stock appears on scanner → audio alert fires
2. **Check float** first — if >40–50M shares, ignore it entirely (don't even check news or chart)
3. **Check news catalyst** — confirm breaking news exists and evaluate type
4. **Check price, relative volume, total volume, percentage change**
5. Only THEN pull up the chart for technical analysis

### Scanner Software
- Ross uses **Day Trade Dash** — custom software he developed with a development team
- Includes multiple scan types: top gainers, high relative volume, breakout alerts
- Also available through Warrior Trading platform

---

## 4. Technical Indicators

All four indicators below should appear on the chart. Ross checks ALL of them before taking any trade — **"if just one of them says no, I don't take the trade."**

### 4.1 Volume Bars
- Displayed in a **separate pane below the price chart**
- Green bars = buying volume (green candle period); Red bars = selling volume (red candle period)
- **What to look for:**
  - More green volume than red volume overall = bullish
  - **Increasing buying volume** as price moves up = strong confirmation
  - High-volume red candle = early exit indicator (sellers entering)
  - More selling volume than buying = do NOT trade
- "Trying to trade without volume is like trying to drive with one eye closed"

### 4.2 Moving Averages (EMAs)
- **Type: Exponential Moving Averages (EMA)**, based on the close
- Three EMAs used on ALL time frames:

| EMA | Color (Ross's setup) | Primary Use |
|-----|---------------------|-------------|
| **9 EMA** | Gray | Intraday support level; first pullback target |
| **20 EMA** | Blue-green | Intraday support level; second pullback target |
| **200 EMA** | Purple | Daily chart resistance/support; major trend indicator |

#### Interpretation:
- **9 EMA**: On 1-min and 5-min charts, price tends to bounce off the 9 EMA during strong trends. This is the first expected support on pullbacks.
- **20 EMA**: If price breaks the 9 EMA, the 20 EMA is the next support. Breaking the 20 typically signals a deeper selloff.
- **200 EMA**: Checked primarily on the **daily chart**. 
  - **Above 200 EMA = bullish** (strong sign of strength)
  - **Below 200 EMA = bearish** (strong sign of weakness)
  - Acts as major resistance/support — short sellers defend it, buyers try to break it
  - On intraday charts (1-min, 5-min), the 200 EMA is usually far from current price and can be ignored
- Moving averages behave differently on different timeframes (200 on daily = 200 days; 200 on 1-min = 200 minutes)

### 4.3 VWAP (Volume Weighted Average Price)
- **No custom settings** — VWAP is standard and identical across all charting platforms
- Represents the **true equilibrium point** — average price including all volume traded
- **Intraday only**: Begins calculating at **4:00 AM** (market open), resets at **4:00 AM** next day
- Same value on all intraday timeframes (1-min, 5-min, etc.)
- Color in Ross's setup: **Orange**

#### Interpretation:
- **Price above VWAP = bullish** → long-biased traders take large positions
- **Price below VWAP = bearish** → short sellers take large positions
- **Break from above to below**: sell signal (shorts get aggressive)
- **Break from below to above**: buy signal (shorts forced to cover by buying → surge of buying pressure)
- VWAP + 9 EMA at same level = **double support** (extra confirmation)

### 4.4 MACD (Moving Average Convergence Divergence)
- **Settings: 12, 26, 9** — standard settings, DO NOT change them
  - "If you change the settings, you'll get the signal at different times and... totally throw off how accurate this signal is"
- Two lines: blue line and orange line

#### Rules:
- **MACD positive (blue above orange)**: Okay to trade long
- **MACD negative (blue below orange)**: **DO NOT trade** — "red light"
- **Crossover from positive to negative**: **Stop buying immediately** — this is the signal that the move is over
- **Crossover from negative to positive**: Resume looking for entries — "green light"
- Works like **"red light, green light"** — that simple
- The MACD tells you when moving averages are **diverging** (stock moving fast, front side of move) vs. **converging** (stock slowing down, back side)

#### Critical Warning:
- MACD **only works on the right stocks** (ones meeting the 5 pillars)
- "You put the MACD on Apple or Tesla, you're just going to see false signals. It's not going to work."

### Indicator Confirmation Rule
**All indicators must agree** before taking a trade:
- Volume profile: more buying than selling ✓
- Moving averages: price above 9 EMA and/or 20 EMA ✓
- VWAP: price above VWAP ✓
- MACD: positive (blue above orange) ✓
- **"One 'no' means no"** — if any single indicator is negative, skip the trade

---

## 5. Chart Patterns

Ross teaches **7 candlestick chart patterns**. His advice: master 1–2 patterns first, add more as you gain experience.

### Pattern 1: Candle Over Candle
- **Description**: Two-candle pattern. One candle forms (can be green or red), and the next candle breaks above the high of the previous candle.
- **Entry trigger**: Buy the moment the next candle breaks above the high of the control candle (the previous candle)
- **Max loss**: Low of the control candle (the candle whose high was broken)
- **Context**: Most powerful at the point of **changing directions** (first candle to make a new high after a pullback) or following a **breakout** through resistance
- **What it shows**: Zooming in (e.g., 10-second candles inside a 1-min candle), the pattern reveals the price dipped briefly then pushed to new highs — buyers in control
- **Key quote**: "I like to buy the first candle over candle setup following a breakout or a change in trend"

### Pattern 2: Micro Pullback
- **Description**: Three to five candle pattern. Stock surges up, pauses very briefly (1–3 small candles of consolidation/slight pullback), then continues higher
- **Entry trigger**: Buy the break above the high of the consolidation range (the micro pullback area)
- **Max loss**: Low of the pullback candles
- **Context**: Occurs during strong momentum — stock hits scanner, is already surging. The micro pullback is a tiny hesitation before continuation.
- **Often appears on scanner alerts** — stock squeezes, brief pause, then continues

### Pattern 3: Breakout / Break of Resistance
- **Description**: Stock tests a resistance level multiple times (half-dollar, whole-dollar, or prior high), then breaks through on increased volume
- **Entry trigger**: Buy on the break through the resistance level, confirmed by the next candle holding above
- **Max loss**: Below the breakout level (if it falls back under, the breakout failed)
- **Key detail**: After multiple failed tests (Ross shows examples of 3 failed attempts), when it finally breaks on higher volume, that's the entry
- **The breakout level that was resistance should become support**

### Pattern 4: Bull Flag / Flat Top Breakout
- **Description**: Stock makes a strong move up (the "pole"), then consolidates sideways or with a slight downward drift (the "flag"), then breaks out to new highs
- **Entry trigger**: Break above the high of the flag/consolidation range
- **Max loss**: Low of the flag consolidation
- **Related to "candle over candle" at the breakout point**

### Pattern 5: First Pullback to 9 EMA
- **Description**: Stock surges up, then pulls back to the 9 EMA on the 1-minute chart. A bottoming tail candle forms at or near the 9 EMA.
- **Entry trigger**: Buy when the first green candle after the pullback breaks the high of the bottoming tail candle
- **Max loss**: Below the 9 EMA / low of the pullback candle
- **Confirmation**: VWAP and 20 EMA should still be below as additional support; MACD still positive

### Pattern 6: Pullback to 20 EMA (Second Support)
- **Description**: Similar to Pattern 5 but deeper — stock breaks the 9 EMA on pullback, finds support at the 20 EMA
- **Entry trigger**: Buy on the first green candle to make a new high after bouncing off the 20 EMA
- **Max loss**: Below the 20 EMA
- **Note**: This is a slightly lower-quality setup than the 9 EMA pullback because the stock had to break the first support level

### Pattern 7: VWAP Reclaim / Reversal
- **Description**: Stock drops below VWAP, trades below it (bearish), then suddenly breaks back above VWAP on volume
- **Entry trigger**: Buy on the break above VWAP (or the micro pullback just after the break)
- **Max loss**: Below VWAP
- **Why it works**: When price breaks back above VWAP, short sellers are forced to cover (buy), creating a surge of buying pressure that accelerates the move
- **Example from transcript**: "$4 all the way up to over $9 a share, up over 100% in 3 minutes"

### Additional Pattern Concepts

#### Bottoming Tail Candles
- Long lower wick, small body — price dropped but buyers rallied it back up
- Signal potential reversal at pullback lows
- Especially powerful at 9 EMA, 20 EMA, or VWAP support levels

#### Topping Tail / Shooting Star
- Long upper wick, small body — price surged but sellers pushed it back down
- Signal potential reversal at highs — beginning of a pullback
- Combined with high-volume red candle = strong exit indicator

#### Doji Candles
- **Standard Doji**: Open and close at same price, wicks both ways — indecision
- **Gravestone Doji**: Open/close at bottom, upper wick — bearish (price popped up but came back)
- **Dragonfly Doji**: Open/close at top, lower wick — bullish (price dipped but recovered)

---

## 6. Time of Day Rules

### Primary Trading Window: 7:00 AM – 10:00 AM Eastern
- This is where Ross makes the **vast majority of his money** — confirmed by historical data, not opinion
- Volume peaks between 7:00 AM and ~10:00–11:00 AM, then declines
- "I'm a big believer in trading during the periods where there's a lot of liquidity"

### Pre-Market (4:00 AM – 9:30 AM)
- Market officially opens at **4:00 AM** for pre-market trading
- 4:00 AM – 7:00 AM: **very light volume** — many commission-free brokers don't allow trading before 7:00 AM
- **7:00 AM = the effective new market open** for active traders
- Breaking news early in the morning drives the biggest pre-market moves
- Ross starts his live broadcast at **7:00 AM Eastern**; sits down at **6:45 AM** to review scanners

### Regular Hours (9:30 AM – 4:00 PM)
- 9:30 AM = official opening bell; historically when most trading began
- Post-pandemic shift: significant volume now occurs **before** 9:30 AM
- Volume gets a small spike at 9:30 AM open, then gradually declines through the day
- Trading after 10:00–11:00 AM is generally lower quality

### Volume Distribution Through the Day
```
Volume
  ▲
  │     ████
  │    █████████
  │   ██████████████
  │  ████████████████████
  │ ██████████████████████████
  │████████████████████████████████         █
  └──────────────────────────────────────────── Time
  7AM    9:30   10AM    12PM    2PM   4PM   8PM
```
- Highest: 7:00 AM – 10:00 AM
- Declining: 10:00 AM onward
- Small spike: 4:00 PM (after-hours earnings)
- Ross focuses his trading on the **7:00 AM – 10:00 AM window**

### Why Time Matters
- More volume = more liquidity = easier to buy and sell
- "We need that volume to support the volatility"
- Trading during low-volume periods leads to choppy, unpredictable price action

---

## 7. Risk Management

### Risk:Reward Ratio
- Target: **2:1 profit-to-loss ratio** (risk $1 to make $2)
- At 2:1 ratio, breakeven accuracy is only **33%**
- In practice, trades often close closer to **1:1** — "we usually come up a little short"
- Aim for 2:1 knowing you'll likely end up around 1:1 to 1.5:1
- **Always think about risk FIRST**, then compare to reward potential

### Daily Goal
- **10% of account** on a good day
- Examples: $2,000 account → $200/day goal; $100 account → $10/day goal
- Expect **2–3 really good days per week**
- Weekly goal: approximately **25% account growth** (3 good days minus 1 red day and 1 break-even day)
- This compounds in early stages but is not sustainable indefinitely

### Max Loss Rules
- **Never lose more in one day than you can make in one day**
- If goal is +10% on good day, max loss should not exceed -10% on bad day
- **Stop trading immediately** when emotionally compromised
- The MACD crossover into negative = **stop buying** (mechanical stop signal)

### When to Stop Trading
1. **MACD crosses negative** — no more entries
2. **Hit daily max loss** — walk away
3. **Emotionally activated** — recognize it, stop immediately
4. **After 10:00 AM** — volume declines, setups deteriorate
5. **Two consecutive losing trades** — reassess before continuing

### Position Sizing Philosophy
- Start with **minimum possible size** (1 share, 10 shares)
- Only increase after proving consistent profitability
- Scale up gradually: $1,000 → $3,000 → $5,000 → $10,000 → $15,000+
- Even with large capital available, **start small** — don't jump to $100,000
- Ross's average share size across his $10M+ challenge: **8,000 shares**
- "Start with a small account and build it up slowly as your track record supports"

### Account Types
- **Cash Account**: Trade with deposited cash; trades settle overnight (T+1); when cash is used up, wait until next day. Good for beginners.
- **Margin Account**: Unlimited daily trades; requires **$25,000 minimum balance** (US brokers only). What Ross uses.
- International brokers don't enforce the $25K minimum — some US traders use offshore brokers as workaround

---

## 8. Trade Execution

### Level 2 Data
- Shows **all open buy and sell orders** on the market for a stock
- Displays every transaction that occurs
- Reveals **clusters of orders at half-dollars and whole-dollars**
- Gives an edge over traders who don't use it
- Essential for reading the order book and understanding supply/demand at specific price levels

### Hot Keys
- **Critical for rapid execution** — no point-and-click, no typing prices or share counts
- Ross's keyboard layout:

| Key | Action |
|-----|--------|
| **Shift + 1** | Buy 1,000 shares |
| **Shift + 2** | Buy 2,000 shares |
| **Shift + 3–0** | Buy 3,000–10,000 shares |
| **Ctrl + Z** | **Panic sell — full position** |
| **Ctrl + X** | Sell half position |
| **Ctrl + C** | Sell quarter position |

- Start simple: memorize **buy, sell full, sell half, sell quarter, cancel all orders**
- Add complex hotkeys only after mastering the basics
- For small accounts: adjust buy hotkeys to smaller sizes (1 share, 10 shares, etc.)

### Half-Dollar / Whole-Dollar Levels
- Stocks trade with **"a great deal of respect for half-dollars and whole-dollars"**
- Orders cluster at $3.00, $3.50, $4.00, $4.50, $5.00, etc.
- These create natural **resistance** (on the way up) and **support** (on the way down)
- As stock approaches a whole/half-dollar: expect initial resistance (profit-taking sell orders)
- If enough buyers, it breaks through to the next level
- **Parabolic moves**: stock breaks through 2–3 levels at once → expect steep pullback after
- Best trades: **first and second pullbacks at the beginning of the move**, not chasing the parabolic

### Entry Timing
- **Ross is a breakout trader**: "I like to buy just before the apex point"
- Gets in at the point where "if this breaks here, it's going to explode"
- Does NOT want to buy and sit holding for a long time
- Two primary entry styles:
  1. **Breakout entry**: Buy on the break of resistance (half-dollar/whole-dollar, prior high, consolidation range)
  2. **Pullback entry**: Buy on the dip to support (9 EMA, 20 EMA, VWAP) with bottoming tail confirmation
- Prefers to be in **as close to the trend change as possible** — minimizes risk
- Looks for the **first candle to make a new high** after a pullback as the precise entry point

### Multi-Timeframe Execution
1. **Daily chart**: Check context — all-time highs/lows, 200 EMA position, major support/resistance
2. **5-minute chart**: Identify overall trend direction and key levels
3. **1-minute chart**: Find precise entries — this is where he executes trades
4. **10-second chart**: Ultra-precise timing for entries and exits

---

## 9. Metrics & Performance Tracking

### What to Track
- **Net profit** (total P/L) — must be green, even if small
- **Average winners** (dollar amount)
- **Average losers** (dollar amount)
- **Accuracy** (win rate percentage)
- **Profitability by stock price** — which price ranges are you profitable in?
- **Profitability by time of day** — when do you make the most?
- **Profitability by setup type** — which patterns work best for you?
- **Number of trades per day** — Ross typically takes only **2 trades per day**

### How to Use Data to Improve
- Ross's turning point came from analyzing his own trade records and discovering a common denominator in winners
- **Sort by biggest winners and biggest losers** — look for relationships and patterns
- Example from transcript: In March, Ross lost money on stocks above $10. He adjusted in April to focus on $2–$10 → made $36,000 (3.6× improvement)
- "If you've been trading and you don't know your own metrics, that's a huge mistake"
- Eliminate outlier losses — these drag down the entire P/L ratio

### Accuracy Targets
- **50% accuracy**: Breakeven with 1:1 P/L ratio
- **60–65% accuracy**: Profitable and sustainable
- **66% accuracy**: Ross's current accuracy (producing $12.3M+ in profits)
- **65–70% accuracy**: Target for traders using A-quality setups
- **75–80% accuracy**: Would produce even larger profits but is aspirational

### P/L Ratio Targets
- Target: **2:1** (aim high)
- Realistic result: **~1:1** (trades close closer to even, but accuracy >50% makes it work)
- Ross's current: average winners ~$1,300, average losers ~$1,300 (approximately 1:1) with 66% accuracy
- Poor P/L ratio is typically caused by **a few outlier trades with huge losses** — eliminate these

### Tools for Tracking
- **TraderVue**: $50/month — import trades, get analytics on price, time, patterns
- **Warrior Trading Simulator**: Includes integrated metrics and reporting
- **Excel/Spreadsheet**: Acceptable (Ross used Excel early in his career)
- Ross does NOT have affiliate relationships with TraderVue, Weeble, or Thinkorswim

---

## 10. What He Avoids

### Stock Types to Avoid
- **Large-cap / household name stocks** (Apple, Tesla, Nvidia, Netflix, Microsoft) — "dominated by institutional traders"; retail trader has no edge
- **Stocks with float >20 million shares** — not enough supply/demand imbalance
- **Stocks with float >40–50 million shares** — doesn't even check the news or chart; immediately ignored
- **Penny stocks** (below $1–$2) — "that would be a mistake" for small account challenges
- **Stocks that are not already up >10%** — no momentum signal
- **Stocks without breaking news** (higher risk; occasionally can work via short squeeze but generally avoided)

### Setups to Avoid
- **Counter-trend trading** — "I don't like to short strong stocks and I don't like to buy weak stocks"
- **Shorting** — creates risk of **infinite loss**; explicitly excluded from small account challenges
- **Trading the "back side"** of a parabolic move as it comes back down
- **Trading when MACD is negative** — red light, no entries
- **Trading stocks with high-volume selling** (more red volume bars than green)
- **Chasing parabolic moves** — don't buy after 2–3 levels are broken at once; wait for pullback
- **Trading after the move is extended** — price going sideways, MACD flat, high selling candles
- **Buying into known resistance** (200 EMA on daily, tested resistance levels) without breakout confirmation

### Behaviors to Avoid
- **Trading without a strategy** — "shooting from the hip"
- **Trading the wrong stocks** — getting sidetracked with low-volume, low-volatility names
- **Overtrading** — "beginner traders who are chronically overtrading... getting in, getting out" hundreds of times
- **Starting with too large an account** — the emotional response to big losses creates spiral
- **Ignoring metrics** — "if you've been trading and you don't know your own metrics, that's a huge mistake"
- **Trading after 10:00 AM** (for small account challenges) — volume declines, quality deteriorates
- **Trading while emotionally compromised** — anger, frustration, desperation
- **Not knowing your exit price before entering** — "if I don't know what I stand to lose, that's a gamble, not a trade"
- **Using brokers with slow execution, no hot keys, or no Level 2 data**

---

## Quick Reference: Scanner Implementation Checklist

Use this to verify the scanner is correctly implementing the strategy:

| Criteria | Requirement | Notes |
|----------|-------------|-------|
| % Change | ≥ 10% up on day | Primary filter |
| Price | $2 – $20 | Sweet spot: $3–$8 |
| Relative Volume | ≥ 5× (vs 50-day avg) | Higher is better |
| Float | ≤ 20M shares | Ideal: <10M; best: <2M |
| News Catalyst | Present | Flag with indicator |
| Time Window | 7:00 AM – 10:00 AM ET | Primary scanning period |
| Sort By | % gain (descending) | Leading gainer = most attention |

### Chart Indicators Required
| Indicator | Settings | Notes |
|-----------|----------|-------|
| Volume Bars | Default | Separate pane; green/red coloring |
| 9 EMA | Length: 9, Close, Exponential | Intraday support |
| 20 EMA | Length: 20, Close, Exponential | Intraday support |
| 200 EMA | Length: 200, Close, Exponential | Daily chart resistance/support |
| VWAP | Standard (no settings) | Intraday only; resets at 4 AM |
| MACD | 12, 26, 9 | Do not modify settings |

### Entry Checklist (All Must Be Yes)
- [ ] Stock meets 5 pillars of selection
- [ ] MACD is positive (blue above orange)
- [ ] Volume profile shows more buying than selling
- [ ] Price is above VWAP
- [ ] Price is at or near support (9 EMA, 20 EMA, or VWAP)
- [ ] Chart pattern identified (candle over candle, micro pullback, breakout, etc.)
- [ ] Risk:reward is at least 2:1
- [ ] Max loss price identified before entry

### Exit Signals
1. MACD crosses from positive to negative
2. High-volume red candle appears
3. Topping tail / shooting star at highs
4. Price breaks below VWAP
5. Daily max loss reached
6. Emotional state compromised
