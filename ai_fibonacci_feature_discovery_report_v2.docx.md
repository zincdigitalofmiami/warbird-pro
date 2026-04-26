

**AI-ASSISTED FEATURE DISCOVERY**

**FOR FIBONACCI TRADING SYSTEMS**

*Distilling Machine Learning Ensembles into Actionable TradingView Indicator Settings Using AutoGluon and SHAP Explainability*

**STATUS: DRAFT / PLANNER BOILERPLATE**

*All configurations, feature sets, data sources, and workflows described in this document are initial planning artifacts. Every section requires independent validation through primary-source research before implementation.*

**2026-04-26 ACTIVE-CONTRACT NOTE:** This report is historical reference only.
The active Warbird plan is indicator-only PineScript AG modeling from
TradingView/Pine outputs. Ignore any sections below that propose external data
stacking, daily ingestion, macro/FRED joins, or warehouse-driven training.

Architecture Reference Document

Halsey / Warbird Trading System

March 2026

# **1\. Executive Summary**

**DRAFT NOTE:** *This entire document is a planning boilerplate. Every configuration, feature list, data source, model parameter, and workflow described herein represents a starting hypothesis that must be validated through primary-source research before any implementation begins. No section should be treated as final specification.*

This document formalizes a complete architecture for using machine learning to discover high-probability trading rules from historical market data, then distilling those rules into simple, human-readable settings for TradingView indicators. The system does not attempt to automate trade execution or replace manual chart analysis. Instead, it uses AutoGluon’s ensemble modeling and SHAP explainability to answer a single question: under what exact numerical conditions do Fibonacci retracement entries have the highest probability of reaching their extension targets?

The core insight driving this architecture is the distinction between using machine learning as a prediction engine versus using it as a discovery tool. Rather than deploying a complex ensemble model in a live production loop, the system trains a high-accuracy model offline, interrogates it with SHAP analysis to extract the specific feature values that drive its highest-confidence predictions, and then exports those values as static input parameters for a TradingView Pine Script indicator. The trader updates these parameters at a cadence appropriate to market conditions—potentially multiple times per trading day—based on fresh SHAP analysis.

A critical design principle: AutoGluon selects its own models, its own ensemble architecture, and its own feature weighting. The system will be fed a broad, healthy selection of up to 60 data types across multiple indicator configurations and timeframes. AutoGluon decides which matter. SHAP explains why. The human decides nothing about model internals—only about what data to offer and how to act on the results.

This approach resolves the fundamental tension between the power of ensemble machine learning and the practical constraints of the TradingView platform, which cannot run Python libraries, persistent memory, or computationally intensive models natively.

# **2\. Core Concept: AI as a Feature Discovery Tool**

## **2.1 The Fundamental Problem**

Fibonacci retracement and extension levels are widely used in technical analysis. A trader identifies a swing high and swing low, calculates standard retracement levels (38.2%, 50%, 61.8%), and enters a trade when price pulls back to one of these levels, targeting extension levels (100%, 123.6%, 161.8%) for profit. The challenge is that not every Fibonacci level holds. A 61.8% retracement may produce a high-probability reversal in one market environment and fail completely in another.

Discretionary traders develop an intuitive feel for which setups “look right,” but this intuition is difficult to quantify, backtest, or transfer to an automated indicator. The question becomes: can a machine learning model, trained on thousands of historical Fibonacci setups enriched with dozens of contextual indicators at varying configurations, identify the specific numerical conditions that separate the winners from the losers—and can it also tell us which indicator settings (lengths, periods, thresholds) are optimal?

## **2.2 The Solution Architecture**

The architecture treats AutoGluon not as a live trading bot, but as an offline research analyst. The workflow proceeds in three distinct phases:

* **Phase 1 – Training:** AutoGluon ingests 2–3 years of historical 15-minute candle data enriched with multi-timeframe features (1-hour, 4-hour, Daily) and external context (VIX, volume profiles, sentiment, economic calendar data). The system is offered a broad selection of up to 60 feature columns—including the same indicator calculated at multiple lengths (e.g., SMA at 9, 10, 11 ... 22, 45, 50, 55, 100, 200). AutoGluon decides which models to train, how to ensemble them, and which features matter. Nothing is pre-selected by the human.

* **Phase 2 – Interrogation:** SHAP analysis is applied to the trained model. For every high-confidence prediction (above 90% probability), SHAP breaks down the contribution of each input feature—including which indicator lengths and which timeframes drove the prediction. This reveals not just that “SMA matters” but that “SMA at length 21 on the 4-hour timeframe was the dominant signal, while SMA at length 50 was noise.”

* **Phase 3 – Implementation:** The extracted Golden Zones are exported as a settings report. The trader takes these numerical thresholds—including the specific indicator lengths and configurations that SHAP identified—and plugs them directly into the input parameters of a TradingView Pine Script indicator. Updates are pushed to the existing Next.js dashboard and/or applied to the TV indicator.

## **2.3 Why This Works**

The critical insight is that you are not trying to replicate the ensemble’s internal logic inside TradingView. You are not copying the “zoo of models.” You are copying what the zoo of models finally boiled down to—the specific data conditions, the specific indicator configurations, and the specific timeframe combinations that were present when the zoo said “this is a 92% probability trade.” Those conditions are simple numerical values that translate directly into indicator input fields.

The ensemble’s value is not in its real-time computation. Its value is in its ability to discover non-obvious relationships—including optimal indicator lengths and setting combinations—across thousands of historical examples that a human would take years to identify through manual chart review.

## **2.4 The “Healthy Selection” Principle**

The system is designed to offer AutoGluon a rich buffet of data without prescribing what should matter. Up to 60 feature columns may be included in any given training run. These features span different indicator types, multiple length configurations for the same indicator, multiple timeframes, and external data sources. The philosophy is: give the model a healthy selection and let it decide. SHAP analysis then acts as the pruning mechanism—identifying which features contributed positively to high-probability predictions and which were noise.

However, this is not a “throw everything at the wall” approach. Each feature added must have a theoretical basis for why it might be relevant to Fibonacci entry success. Adding random or redundant data introduces noise that can degrade model performance even with AutoGluon’s built-in feature selection. The balance is: broad but intentional.

# **3\. AutoGluon: The Training Engine**

## **3.1 What AutoGluon Does**

AutoGluon is an open-source AutoML framework developed by Amazon. Its TabularPredictor module automates the full machine learning pipeline: feature engineering, model selection, hyperparameter tuning, and ensemble construction. When given a labeled dataset and a target column, it trains multiple model families simultaneously, stacks them in layers, and produces a final predictor that combines their outputs through learned weights.

AutoGluon selects its own models. The human does not choose XGBoost, LightGBM, Neural Networks, or any specific algorithm. The best\_quality and extreme\_quality presets allow AutoGluon to explore its full repertoire of model families and ensemble strategies. The final predictor may be a single model, a bagged set, a multi-layer stack, or any combination AutoGluon determines is optimal for the specific dataset and target. The human’s role is to provide good data and correct labels—nothing more.

## **3.2 Suggested Training Configuration**

**DRAFT NOTE:** *The following configuration is a suggested starting point and needs to be evaluated with research. Before finalizing any training parameters, the implementer must conduct thorough research on the AutoGluon documentation site (https://auto.gluon.ai), identifying all available options, model families, AI integrations, workflow configurations, and add-ons. AutoGluon has hundreds of highly capable, preconfigured add-ons and extensions that may dramatically improve results for this specific use case. Do not accept these defaults without investigating alternatives.*

| Parameter | Suggested Starting Value | Research Required |
| :---- | :---- | :---- |
| Preset | best\_quality or extreme\_quality | Evaluate all available presets. The AG docs describe trade-offs for each. Test medium\_quality first for rapid iteration, then scale up. |
| Eval Metric | f1 | Investigate all supported metrics for binary classification. Consider precision, recall, log\_loss, roc\_auc, and custom metrics depending on the cost asymmetry of false positives vs. false negatives in trading. |
| Time Limit | 7200–14400 seconds | This is highly hardware-dependent. Profile actual training times on target hardware (Mac Mini M4 Pro 24GB) and adjust. Longer is not always better—diminishing returns exist. |
| Num Stack Levels | 1–2 | Research the stacking documentation. More levels increase compute exponentially. Determine whether the feature set benefits from deep stacking or whether single-level ensemble is sufficient. |
| Num Bag Folds | 5–8 | Cross-validation fold count. Research the trade-off between variance reduction and training time. Market data is sequential—investigate whether time-series-aware splitting is available. |
| Feature Generator | Default (auto) | AG has advanced feature generation options. Research whether the auto generator handles the indicator-length variants appropriately or whether manual feature groups are needed. |
| Hyperparameter Tuning | Default (auto) | Research AG’s hyperparameter search strategies. Bayesian optimization may outperform random search for this feature volume. |

## **3.3 AutoGluon Ecosystem Research Requirements**

Before any training begins, the following research must be completed against the official AutoGluon documentation and community resources:

* **Model Families:** Identify every model family AutoGluon can train (tree-based, neural, linear, k-nearest-neighbors, etc.). Understand which families are included in each preset and whether additional families can be enabled. Do not assume the defaults are optimal.

* **Add-Ons and Extensions:** AutoGluon has hundreds of preconfigured add-ons, plugins, and community extensions. Research which ones are relevant to tabular classification on financial time-series data. Examples include custom feature generators, specialized data augmentation, and domain-specific preprocessing pipelines.

* **AI Integrations:** Research whether AutoGluon supports integration with external AI models (e.g., foundation models, pre-trained embeddings) that could enhance feature representation for market data.

* **Workflow Configurations:** Investigate AutoGluon’s support for incremental training, warm-starting from previous models, and partial retraining—all of which are critical for the daily/intraday update cadence required by this system.

* **Time-Series Awareness:** Determine whether TabularPredictor has time-aware splitting options to prevent data leakage (future data leaking into training folds). If not, research TimeSeriesPredictor as an alternative or supplementary approach.

* **Distillation and Interpretability:** Research predictor.distill(), RuleFit models, and any built-in interpretability tools. These may complement or simplify the SHAP extraction workflow.

## **3.4 Target Variable Construction**

The target (label) column is a binary classification: 1 if the trade was a winner, 0 if it was a loser. The definition of “winner” must be precise and consistent across the entire dataset:

* **Win (1):** After price touches the Fibonacci retracement entry level (e.g., 61.8%), price subsequently reaches the Fibonacci extension target (e.g., 100% or 161.8%) before hitting the defined stop-loss level.

* **Loss (0):** After touching the entry level, price hits the stop-loss (typically the 78.6% or series-break level) before reaching the extension target.

The stop-loss definition should align with the Halsey ruleset: a 61.8% series break invalidation, meaning the trade is considered failed if price retraces beyond the 61.8% level of the prior swing structure that defined the entry.

## **3.5 Model Selection Philosophy: Let AutoGluon Decide**

This system does not prescribe which models AutoGluon should use. No model family is preferred, required, or excluded. The human’s job is to provide clean, well-labeled data with a broad feature set. AutoGluon’s job is to determine which model architecture, which ensemble strategy, and which feature subset produces the highest-accuracy predictions.

After training, the system inspects what AutoGluon chose (via predictor.leaderboard() and predictor.info()) for research and documentation purposes—but these choices are not overridden. If AutoGluon determines that a single LightGBM model outperforms a 20-model stack for this specific dataset, that is the result. The SHAP extraction workflow operates identically regardless of the underlying model architecture.

# **4\. Multi-Timeframe Feature Engineering**

## **4.1 The Timeframe Hierarchy**

The system uses four timeframes, each serving a distinct analytical role. Every row in the training dataset represents a single 15-minute candle where a Fibonacci entry condition was detected. That row is enriched with snapshot values from the higher timeframes at that same moment in time.

| Timeframe | Role | Example Features (Subject to Change) |
| :---- | :---- | :---- |
| Daily | Trend Bias / Macro Context | SMA/EMA at multiple lengths, ADX, daily range percentile, distance to key support/resistance |
| 4-Hour | Major Market Structure | Market structure state, RSI, distance to significant S/R zones, order block proximity, SMA/EMA variants |
| 1-Hour | Local Momentum and Flow | Volume relative to SMA variants, RSI momentum, EMA crossover states, VWAP distance |
| 15-Minute | Entry Trigger (Fibonacci) | Fib level touched, candle rejection size, distance to exact Fib level, RSI at entry, local volume |

## **4.2 Indicator Length Permutations**

A key innovation of this system is that indicators are not tested at a single length. Instead, multiple lengths are included as separate feature columns, allowing AutoGluon and SHAP to discover which specific configuration is optimal for each timeframe and market condition.

**DRAFT NOTE:** *The length ranges below are starting hypotheses. Research is required to determine whether additional ranges, finer granularity, or different indicator types should be included. The total feature count must remain manageable (target: 60 or fewer columns) to avoid excessive noise.*

| Indicator | Length Ranges to Test | Resulting Feature Columns |
| :---- | :---- | :---- |
| Simple Moving Average (SMA) | 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 50, 55, 90, 100, 110, 200 | SMA\_9, SMA\_10, ... SMA\_200 (price distance or slope per timeframe) |
| Exponential Moving Average (EMA) | 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 50, 55, 90, 100, 110, 200 | EMA\_9, EMA\_10, ... EMA\_200 (same treatment as SMA) |
| RSI | To be determined by research | Multiple RSI lengths as separate columns |
| ATR | To be determined by research | Multiple ATR lengths as separate columns |

Important: not every length variant needs to appear on every timeframe. The feature matrix should be designed intentionally. For example, SMA\_200 is meaningful on the Daily chart but may be noise on the 15-minute chart. The initial feature set is the hypothesis; SHAP analysis is the validation. Features that SHAP consistently identifies as noise across multiple training runs should be removed in subsequent iterations.

The goal is for SHAP to tell us, for example: “On the 4-hour timeframe, SMA at length 21 was the dominant signal. SMA at length 50 contributed nothing. On the Daily, EMA at length 55 outperformed all other moving average configurations.” These specific length-timeframe combinations become the indicator settings in the TradingView Pine Script.

## **4.3 Feature Categories**

**DRAFT NOTE:** *The feature categories below are not set in stone. Features will be added and removed as research progresses. The system is designed to accommodate up to 60 feature columns per training run. All features listed are starting hypotheses.*

### **4.3.1 Fibonacci-Specific Features**

**CRITICAL:** The Fibonacci indicator used on the actual TradingView chart must be the exact same indicator used to generate the training data for the model. Any difference between the TV chart indicator and the model’s Fibonacci calculations—whether in the algorithm, the swing detection logic, the calculation method, or any parameter—will cause catastrophic mismatch between what the model learned and what the indicator shows live. This is a non-negotiable requirement.

**CRITICAL:** All indicators used in the system—Fibonacci and otherwise—must be verified as non-repainting. An indicator that repaints changes its historical values after the fact. If repainting indicators are used to generate training data, the model will learn from “perfect hindsight” data that never existed in real time. The model will appear highly accurate in backtesting and fail catastrophically in live trading. Every indicator must be independently verified for non-repainting behavior before inclusion.

* Fib Level Touched: Which retracement level price reached (38.2%, 50%, 61.8%).

* Distance to Fib Level: How close price actually came to the theoretical Fibonacci level, measured in ticks or as a percentage.

* In Golden Zone: A boolean flag indicating whether price is within the 50%–61.8% retracement zone.

* Extension Target Distance: The distance from entry to 100%, 123.6%, and 161.8% extension targets, normalized by ATR.

### **4.3.2 Volatility and Regime Features**

**DRAFT NOTE:** *The volatility and regime features listed below require deep exploration through academic research before finalization. Authoritative sources to consult include: TradingView’s indicator library and documentation, LuxAlgo’s published research and indicator methodology, university studies on market microstructure and volatility regimes, NinjaTrader’s community research, brokerage research departments (e.g., Interactive Brokers, TD Ameritrade/Schwab research), peer-reviewed journals on quantitative finance, and the CBOE’s VIX methodology papers. No volatility or regime feature should be included without understanding its theoretical basis, calculation methodology, and known limitations from authoritative sources.*

* VIX Level: The CBOE Volatility Index value at the time of entry. Must be sourced from Databento Standard subscription or FRED (Federal Reserve Economic Data).

* VIX Rate of Change: The percentage change in VIX over a configurable lookback. Multiple lookback lengths should be tested as separate features.

* Hurst Exponent: A measure of trending vs. mean-reverting behavior. Requires careful implementation—research the appropriate lookback window and calculation method.

* Choppiness Index: Measures consolidation vs. trending conditions. Research the interaction between Choppiness Index thresholds and Fibonacci level reliability.

* ADX (Average Directional Index): Measures trend strength. Multiple lookback lengths should be tested.

* Additional regime features to be identified through academic research. This list is explicitly incomplete.

### **4.3.3 Volume and Liquidity Features**

**DRAFT NOTE:** *Volume and liquidity features are not set in stone. The features below are starting hypotheses. All volume data must be available through the Databento Standard subscription ($179/mo). Research is needed on what volume and liquidity metrics Databento provides and which additional calculations can be derived from the raw data.*

* Volume Relative to SMA: Current volume divided by SMA of volume at multiple lookback lengths.

* VWAP Distance: Distance from price to Volume-Weighted Average Price.

* Volume Profile Point of Control (POC): Whether the Fibonacci level aligns with a high-volume node. Availability through Databento must be verified.

* Delta Volume / Order Flow: If available through Databento, net buying vs. selling pressure at the Fibonacci level.

* Additional liquidity metrics to be identified through research into Databento’s data offerings and TradingView’s community indicators for volume analysis.

### **4.3.4 Sentiment and Economic Calendar Features**

**CRITICAL IMPORTANCE:** Economic calendar and news sentiment features are highly important to this system. Markets react both on the news hitting and in the lead-up to scheduled announcements. The model must capture: (1) the probability of market direction after a news event hits, (2) the sentiment bias of what the market expects the announcement to be, and (3) the alternative actions—what happens if the announcement contradicts expectations. This is not optional. Sentiment scoring is mandatory.

* **Economic Calendar Flag:** A categorical or multi-valued feature indicating proximity to high-impact economic events (FOMC, NFP, CPI, GDP, etc.). Must include: time until next announcement, time since last announcement, expected vs. actual values (for historical data), and the magnitude of the expected impact.

* **Sentiment Scoring:** A numerical sentiment score derived from financial news. A free news source must be identified—this is a hard constraint. Candidates include: FRED (economic data with implicit sentiment from revisions and surprises), free financial news APIs, RSS feeds from major financial outlets processed through FinBERT or a similar NLP model.

* **Expectation vs. Reality Modeling:** The model should capture not just “a news event happened” but the divergence between market expectations and actual results. A positive surprise (actual better than expected) in a bearish-sentiment environment creates different Fibonacci dynamics than the same surprise in a bullish environment.

* **Pre-Announcement Behavior:** Feature flags for the 1-hour, 4-hour, and 24-hour windows before scheduled announcements. Markets often compress ranges and reduce Fibonacci reliability during these windows.

## **4.4 Data Source Constraints**

All data used in the system must be available through one of two sources:

* **Databento Standard Subscription ($179/mo):** Primary source for price data (OHLCV), volume data, and any additional market microstructure data available at this tier. Research is required to catalog exactly what data types are available at the Standard tier.

* **FRED (Federal Reserve Economic Data):** Free, authoritative source for macroeconomic data including VIX historical values, interest rates, economic indicators, and other macro context features.

* **Free News/Sentiment Sources:** A free source for financial news must be identified for sentiment scoring. This is a research requirement. The source must provide sufficient coverage of market-moving events and be available programmatically (API or RSS).

No additional paid data subscriptions should be assumed or recommended without explicit approval. If a feature requires data not available through Databento Standard or FRED, that feature must be flagged as blocked until a free or already-subscribed source is identified.

# **5\. Database Schema: SHAP-Addressable Structure**

## **5.1 Design Principle**

The database schema must be designed so that SHAP analysis results can be stored, queried, and compared across training runs. Since the feature set is dynamic (features will be added and removed over time, and indicator lengths will be tested in ranges), the schema must accommodate metadata about what was tested, what SHAP found, and what changed between runs.

## **5.2 Core Tables**

**DRAFT NOTE:** *The following table structure is a starting point. Schema design requires validation against actual data volumes, query patterns, and the specific output format of the SHAP extraction scripts.*

| Table | Purpose | Key Columns |
| :---- | :---- | :---- |
| training\_runs | Metadata for each AutoGluon training session | run\_id, timestamp, preset\_used, dataset\_date\_range, feature\_count, model\_accuracy, notes |
| features\_catalog | Registry of all features ever tested | feature\_id, feature\_name, indicator\_type, indicator\_length, timeframe, data\_source, is\_active |
| training\_features | Which features were included in each training run | run\_id (FK), feature\_id (FK), was\_selected\_by\_ag (bool) |
| shap\_results | SHAP Golden Zone output per feature per run | run\_id (FK), feature\_id (FK), golden\_zone\_min, golden\_zone\_max, ai\_weight, positive\_contribution\_pct |
| shap\_indicator\_settings | SHAP-discovered optimal indicator configurations | run\_id (FK), indicator\_type, optimal\_length, optimal\_timeframe, shap\_weight, notes |
| prediction\_snapshots | Periodic prediction outputs for dashboard/TV updates | snapshot\_id, run\_id (FK), timestamp, symbol, prediction\_probability, features\_json |
| economic\_events | Economic calendar data for news/sentiment features | event\_id, event\_type, scheduled\_time, expected\_value, actual\_value, surprise\_magnitude, sentiment\_score |

## **5.3 SHAP Traceability**

The schema must support answering questions like: “What indicator length did SHAP prefer for SMA on the 4-hour timeframe in last week’s training run versus this week’s?” and “Which features have been consistently irrelevant across the last 10 training runs and should be removed?” This traceability allows the system to evolve its feature set intelligently rather than guessing.

The shap\_indicator\_settings table is particularly important. In a perfect world, SHAP doesn’t just tell you which indicators matter—it tells you the optimal settings for those indicators (length, period, threshold). This table captures those discoveries so they can be directly applied to the TradingView indicator inputs.

# **6\. SHAP Explainability: Extracting the Golden Zones**

## **6.1 What SHAP Does**

SHAP (SHapley Additive exPlanations) is a game-theory-based framework for interpreting machine learning predictions. For every individual prediction a model makes, SHAP assigns a contribution value to each input feature, quantifying exactly how much that feature pushed the prediction higher or lower relative to the baseline.

In trading terms: if AutoGluon predicts a 92% probability that a specific Fibonacci entry will reach its extension target, SHAP decomposes that prediction into contributions like “+15% because VIX was 17.5, \+12% because 4h SMA\_21 distance was positive, \+8% because volume was 1.6x SMA\_20, −3% because EMA\_50 on 1h was flat.”

This decomposition is the mechanism by which complex ensemble logic gets translated into simple numerical thresholds. The trader does not need to understand the internal weights of any model. They need to know that VIX below 19, 4h SMA at length 21, and 1h volume above 1.5x SMA\_20 are the conditions under which the AI’s confidence was highest.

## **6.2 Three Methods for Extracting Rules**

### **6.2.1 The Anchor Method (Individual Trade Logic)**

For any single high-probability prediction, SHAP produces a force plot showing the exact features and values that drove that specific prediction. This is useful for understanding why the model liked a particular trade setup. The limitation is that it explains individual predictions, not global patterns.

### **6.2.2 The Partial Dependence Method (Finding Sweet Spots)**

SHAP dependence plots show how a single feature’s value correlates with prediction probability across the entire dataset. These plots reveal the “sweet spot” for each indicator and each indicator length—the numerical range where the model’s confidence is maximized. These ranges become the Min/Max input settings for TradingView indicator parameters.

### **6.2.3 The Representative Sample Method (Prototype Trade)**

This method filters the historical dataset for only those trades where AutoGluon assigned a probability above 90% and the trade was actually a winner. By computing the mean, minimum, and maximum of each feature across this filtered subset, you derive the “common denominator” of winning trades.

## **6.3 SHAP for Indicator Settings Discovery**

In a perfect world, SHAP does not just identify which data types matter—it identifies the optimal indicator settings as well. Because the feature set includes the same indicator (e.g., SMA) at multiple lengths (9 through 200), SHAP analysis naturally reveals which length configurations contributed most to high-probability predictions. If SMA\_21 on the 4-hour consistently has high positive SHAP values while SMA\_50 on the same timeframe has near-zero values, that is a direct recommendation for the TradingView indicator: use SMA at length 21\.

**DRAFT NOTE:** *To keep this manageable in the initial implementation, indicator settings discovery via SHAP may be supplemented by an AI Agent trained specifically on this task—a Skill that understands the indicator configuration space and can interpret SHAP outputs as specific Pine Script input recommendations. This Agent/Skill approach is a future enhancement to validate.*

## **6.4 The SHAP Update Workflow**

The operational workflow runs at two cadences:

* **Full Model Retrain \+ SHAP Extraction:** Weekly minimum on weekends, using the most recent 2–3 year rolling window. This captures structural shifts in feature importance and indicator length preferences.

* **SHAP Extraction Only (No Retrain):** Daily on trading days before the session opens. Runs the existing model against the most recent data window to refresh Golden Zone parameters. Prediction updates may be generated multiple times per day during trading hours for the dashboard.

Results are stored in the shap\_results and shap\_indicator\_settings database tables, enabling comparison across runs and trend analysis of which features are gaining or losing importance over time.

# **7\. Market Regime Detection: The Master Filter**

## **7.1 Why Regime Matters for Fibonacci**

Fibonacci retracement levels are fundamentally trend-following tools. They work by identifying pullbacks within a directional move and projecting where the move will resume. In a trending market, these levels act as genuine support and resistance zones. In a ranging or choppy market, the same levels are noise. Without a regime filter, the indicator will generate signals in both environments, inflating the loss rate during consolidation periods.

## **7.2 Regime Detection Research Requirements**

**DRAFT NOTE:** *Regime detection methods must be explored deeply through academic research before any specific method is selected. This is not a feature to configure casually. Consult: TradingView’s indicator library for community-built regime detectors, LuxAlgo’s published research on regime classification, university studies on Hurst exponent estimation and market microstructure, NinjaTrader’s community research on regime-aware strategies, brokerage research papers (Interactive Brokers, Schwab, etc.), and peer-reviewed quantitative finance journals. AutoGluon and SHAP will ultimately decide which regime indicator matters most, but the initial candidate set must be grounded in credible research.*

* Hurst Exponent: Trending (H \> 0.5), mean-reverting (H \< 0.5), random walk (H ≈ 0.5). Requires careful selection of lookback window and calculation method.

* Choppiness Index: Bounded 0–100, with Fibonacci-derived thresholds (38.2 and 61.8) as natural classification boundaries.

* ADX on Daily Timeframe: Values above 25 indicate trend; below 20 indicate range. Multiple lookback lengths should be tested.

* Additional candidates to be identified through academic research. This list is explicitly incomplete.

# **8\. TradingView Implementation: The Output Layer**

## **8.1 TradingView Ecosystem Research Requirements**

**DRAFT NOTE:** *Before building the Pine Script indicator, comprehensive research must be conducted on TradingView’s full ecosystem—similar in scope and rigor to the AutoGluon ecosystem research described in Section 3.3. The goal is to discover every available tool, built-in function, community resource, and data source that can be leveraged within Pine Script to parallel the features used in the AutoGluon model.*

Research areas include:

* **Built-in Functions:** Catalog every built-in Pine Script function relevant to the feature set (ta.sma, ta.ema, ta.rsi, ta.atr, ta.vwap, ta.choppiness, ta.adx, etc.). Understand their exact calculation methods to ensure parity with the model’s feature calculations.

* **Community Indicators:** TradingView’s community has thousands of published indicators. Research indicators built for sentiment analysis, volume profiling, liquidity analysis, market regime detection, and uncertainty measurement. The relevant calculation logic from these community indicators can be extracted and incorporated into the custom indicator. This is not about using someone else’s indicator as-is—it is about studying the mathematics and adapting the relevant parts.

* **News and Sentiment in Pine Script:** Research whether Pine Script has any built-in or community-supported methods for accessing news data, economic calendar data, or sentiment scores within the script environment. If not, determine the best architecture for feeding external sentiment data into the indicator (e.g., through a cloud-hosted data bridge).

* **Volume and Liquidity Tools:** Research Pine Script’s capabilities for volume profile, delta volume, cumulative volume delta, order flow approximation, and other liquidity metrics. Determine which can be calculated natively and which require external data.

* **Data Feeds and Security Requests:** Research the full capabilities of request.security() for multi-timeframe data, request.financial() for fundamental data, and any other request functions that could provide additional context to the indicator.

## **8.2 The Pine Script Indicator Structure**

The TradingView indicator serves as the execution layer. It contains no machine learning logic. It is a conventional Pine Script indicator whose input parameters are populated with the numerical values discovered by the SHAP analysis pipeline. The indicator’s structure follows a hierarchical gating pattern:

* Gate 1 – Regime Filter: Is the market currently in a trending regime (per AI-discovered thresholds)?

* Gate 2 – Daily Trend Filter: Is the Daily trend bias aligned with the trade direction (per AI-discovered SMA/EMA length and slope thresholds)?

* Gate 3 – 4-Hour Structure Filter: Is the 4-hour market structure and RSI within the AI-discovered Golden Zone?

* Gate 4 – 1-Hour Momentum Filter: Does the 1-hour volume and momentum confirm sufficient participation?

* Gate 5 – 15-Minute Trigger: Has price touched the Fibonacci retracement level with the precision required by the AI-discovered touch buffer?

* Gate 6 – Economic Calendar Gate: Is the market within a configurable exclusion window around high-impact news events?

Only when all gates pass simultaneously does the indicator fire a signal. Each gate’s threshold values come directly from the SHAP-extracted Golden Zones.

## **8.3 Indicator-Model Parity**

**NON-NEGOTIABLE:** The calculations performed inside the Pine Script indicator must produce identical numerical values to the calculations used to generate the training data. If the model was trained on SMA\_21 calculated as a simple arithmetic mean of the last 21 closing prices, the Pine Script must use ta.sma(close, 21)—not a weighted average, not an EMA, not a custom smoothing function. Any divergence between the model’s feature calculations and the indicator’s calculations will produce false signals.

This parity requirement extends to the Fibonacci indicator, all moving averages, RSI, ATR, volume calculations, and every other feature that appears in both the model and the Pine Script. A formal verification step must be included in the deployment process: compare the indicator’s output values against the model’s feature values for a sample of historical candles and confirm exact numerical agreement.

## **8.4 Why Pine Script Cannot Run the Model Directly**

* No Persistent Memory: Pine Script recalculates from scratch on every bar.

* No External Libraries: The sandboxed environment does not support Python.

* Compute Limits: Script execution is limited to approximately 20–40 seconds per bar.

* No Network Access: Pine Script cannot make HTTP requests to an external server.

These constraints are precisely why the architecture separates the intelligence layer (AutoGluon \+ SHAP, running in Python) from the execution layer (Pine Script, running in TradingView).

## **8.5 The Webhook Alternative**

For traders who want real-time AI predictions without manual parameter updates, a webhook-based architecture is available. TradingView’s alert system sends a JSON payload to a Python server running Flask or FastAPI, which feeds the payload into the trained AutoGluon model and returns a probability score. This provides real-time adaptive predictions but requires a hosted Python server, broker API integration, and latency management.

# **9\. Dataset Specifications**

## **9.1 Recommended Data Volume**

| Parameter | Recommendation | Rationale |
| :---- | :---- | :---- |
| Historical Depth | 2–3 years | Provides \~50,000+ 15-minute candles. Captures regime changes without including obsolete patterns. |
| Why Not 10 Years | Model confusion | Market microstructure changes significantly over a decade. Including obsolete data introduces noise. |
| Minimum Labeled Trades | 500+ | The model needs several hundred win/loss examples to learn meaningful patterns. |
| Timeframe Resolution | 15-minute candles | Primary trigger timeframe. Higher timeframes are snapshot features per 15m row. |

## **9.2 Data Sources**

* **Price Data:** Databento Standard subscription ($179/mo). Verify availability of MES futures 15m/1h/4h/Daily OHLCV at this tier.

* **VIX and Macro Data:** FRED (Federal Reserve Economic Data)—free, authoritative, programmatic access.

* **Economic Calendar:** Research free sources. FRED provides some economic release data. Alternatives include free APIs from financial data providers.

* **News/Sentiment:** A free source must be identified. This is a hard requirement. Candidates: RSS feeds from Reuters, Bloomberg (free tier), or financial news aggregators processed through FinBERT or similar NLP.

* **Volume/Liquidity:** Included in Databento price data. Research what additional volume metrics (delta, profile) are available at Standard tier.

# **10\. Model Training and Maintenance**

## **10.1 Training and Update Cadence**

| Cadence | Activity | Purpose |
| :---- | :---- | :---- |
| Weekly (weekends) | Full model retrain (2–4+ hours, best\_quality) | Rolling 2–3 year window. Incorporates the most recent week’s data. Resets feature importance baseline. |
| Daily (pre-session, trading days) | SHAP extraction \+ prediction refresh | Updates Golden Zone parameters. Generates fresh probability snapshots for the trading day. |
| Intraday (multiple times per trading day) | Prediction updates only | Run the existing model against current-candle data to refresh probability scores. Push updates to the Next.js dashboard. |
| Monthly | Deep retrain \+ feature set review | Extreme\_quality preset. Evaluate whether features should be added/removed. Review SHAP trend data across past month’s runs. |

## **10.2 Model Decay**

Machine learning models trained on market data experience “model decay” as market regimes shift. The regime detection features partially mitigate this, but periodic retraining is still necessary. The weekly retrain cadence is the minimum acceptable frequency. During periods of high volatility or regime transition, daily retrains may be warranted.

## **10.3 Hardware Requirements**

**DRAFT NOTE:** *Hardware requirements depend on the final feature count, dataset size, and preset used. The values below are estimates for the Mac Mini M4 Pro (24GB) and need to be validated through actual profiling.*

* Minimum for weekly retrains: 16 GB RAM, 8-core CPU.

* Target hardware: Mac Mini M4 Pro (24GB), multi-core Apple Silicon. AutoGluon’s tree-based models benefit from high core counts.

* GPU Acceleration: On Apple Silicon, the MPS backend provides partial acceleration for PyTorch-based model components.

# **11\. Integration Risks and Mitigations**

| Risk | Description | Mitigation |
| :---- | :---- | :---- |
| Overfitting | Model learns noise-specific patterns that don’t generalize to live trading. | 5–8 bag folds, multi-layer stacking, strict out-of-sample validation (most recent 3 months held out). |
| Indicator Repainting | Repainting indicators produce training data that doesn’t match live behavior. | Every indicator verified as non-repainting before inclusion. Formal verification step in deployment. |
| Feature Noise | Too many irrelevant features degrade model performance. | Start with theoretically grounded features. Use SHAP to prune. Remove features with consistently zero SHAP contribution. |
| Indicator-Model Mismatch | Pine Script calculations diverge from model feature calculations. | Formal parity verification: compare indicator outputs against model features for sample candles. |
| Data Source Gaps | Required data not available through Databento Standard or FRED. | Catalog available data before designing features. Flag blocked features early. |
| Static vs. Dynamic | SHAP parameters are snapshots; markets shift intraday. | Daily SHAP extraction \+ intraday prediction refreshes via dashboard. |
| Latency (Webhook Path) | 1–3 second webhook delay. | 15-minute entries tolerate this. For faster execution, use dashboard push. |
| Sentiment Data Quality | Free news sources may have coverage gaps. | Multiple free sources aggregated. Coverage gaps flagged in prediction confidence. |

# **12\. Open Questions: Things That Need to Be Figured Out**

*The following items are unresolved design decisions, research questions, and architectural choices that must be addressed before or during implementation. This section is the active “to figure out” backlog for the project.*

## **12.1 Inference Frequency and Freshness**

* Since trading is live and setups appear frequently, how often does the SHAP extraction need to run to provide fresh insight? Is daily pre-session sufficient, or do intraday conditions change fast enough that mid-session refreshes are necessary?

* What is the fastest way to run inference (prediction only, no retrain) on the current model? Can this be done in under 30 seconds for a single 15-minute candle’s feature set?

* Is there a way to “warm start” or incrementally update the model with new data without a full retrain? AutoGluon’s documentation must be researched for this capability.

* What is the minimum viable prediction latency for the intraday update loop? If the trader needs a probability update within 60 seconds of a new 15-minute candle closing, can the current hardware and model architecture support that?

## **12.2 Dashboard vs. TradingView Connection**

* Should prediction updates be pushed to the existing Next.js dashboard (already built) instead of building a direct connection to TradingView? The dashboard is already operational and can display probability scores, Golden Zone ranges, and regime status without requiring TV integration.

* Can the dashboard serve as the “single pane of glass” that shows the AI’s current assessment alongside the TV chart, rather than trying to embed AI logic inside Pine Script?

* If using the dashboard approach: should the trader update TV indicator inputs manually from the dashboard display, or should there be an automated pipeline that exports settings to a file/API that the TV indicator can read?

* What is the user experience trade-off between “look at dashboard for AI verdict, look at TV for chart” versus “everything on one TV screen”?

## **12.3 Data Pipeline Questions**

* What is the exact catalog of data available through Databento Standard at $179/mo? This must be enumerated before finalizing the feature set.

* What free news/sentiment sources are viable? What is their API rate limit, coverage, and latency? Can FinBERT sentiment scoring run fast enough for daily updates?

* How should economic calendar data be sourced and structured? Is there a free API with forward-looking event schedules and consensus estimates?

* How do we handle the “expected vs. actual” sentiment modeling for economic events in the training data? Historical consensus estimates may not be easily available for free.

## **12.4 Feature Engineering Questions**

* With up to 60 features and multiple indicator length variants, what is the risk of the feature matrix becoming too sparse or too correlated? Should dimensionality reduction (PCA, etc.) be applied before training, or should AutoGluon handle this internally?

* How do we ensure that the SMA/EMA length variants (9–22, 45–55, 90–110, 200\) don’t introduce harmful multicollinearity? SMA\_20 and SMA\_21 are highly correlated—does this help or hurt AutoGluon’s performance?

* Should indicator lengths be tested as continuous features (the length value itself) rather than as separate columns? This would dramatically reduce the feature count but changes the modeling approach.

## **12.5 TradingView Indicator Questions**

* How many input parameters can a Pine Script indicator practically support before the settings panel becomes unusable?

* Can Pine Script read from an external data source (Google Sheets, JSON endpoint) to auto-update its input parameters without manual entry?

* What is the best approach for ensuring Fibonacci indicator parity between the Python model and the TV chart? Should the same Fibonacci calculation code be written in both Python and Pine Script from a shared specification?

## **12.6 AI Agent / Skill for Indicator Settings**

* Can an AI Agent (a Skill in the project’s framework) be trained or configured to interpret SHAP output and automatically generate Pine Script input parameter recommendations?

* Would this Agent operate as a post-processing step after SHAP extraction, translating numerical ranges into formatted indicator settings?

* What is the scope of this Agent? Should it only handle SHAP-to-Pine-Script translation, or should it also advise on feature set changes, retraining triggers, and regime classification?

# **13\. Reference Links and Learning Resources**

## **13.1 AutoGluon**

* AutoGluon Tabular Quick Start: https://auto.gluon.ai/stable/tutorials/tabular/tabular-quick-start.html

* AutoGluon Tabular In-Depth: https://auto.gluon.ai/stable/tutorials/tabular/tabular-indepth.html

* AutoGluon TabularPredictor API: https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.html

* AutoGluon Model Distillation: https://auto.gluon.ai/stable/api/autogluon.tabular.TabularPredictor.distill.html

* AutoGluon Time Series: https://auto.gluon.ai/dev/tutorials/timeseries/forecasting-quick-start.html

* AutoGluon Add-Ons and Community: Research required—catalog available extensions.

## **13.2 SHAP Explainability**

* SHAP Documentation: https://shap.readthedocs.io/en/latest/

* SHAP KernelExplainer API: https://shap.readthedocs.io/en/latest/generated/shap.KernelExplainer.html

* SHAP for Trading Patterns: https://towardsdatascience.com/using-shap-values-to-explain-how-your-machine-learning-model-works

## **13.3 TradingView / Pine Script**

* Pine Script Language Reference v5: https://www.tradingview.com/pine-script-reference/v5/

* Pine Script User Manual: https://www.tradingview.com/pine-script-docs/

* request.security() Docs: https://www.tradingview.com/pine-script-reference/v5/\#fun\_request.security

* TradingView Community Indicators: Research required—catalog sentiment, volume, and regime indicators.

## **13.4 Market Regime and Volatility Research**

* Hurst Exponent: https://en.wikipedia.org/wiki/Hurst\_exponent

* Choppiness Index: https://www.investopedia.com/terms/c/choppinessindex.asp

* LuxAlgo Research: https://www.luxalgo.com/ (research their published methodology)

* University Studies: Research required—identify relevant papers on market microstructure and regime detection.

## **13.5 Data Sources**

* Databento: https://databento.com/ (verify Standard tier data availability)

* FRED: https://fred.stlouisfed.org/ (free economic data)

* FinBERT: https://huggingface.co/ProsusAI/finbert (sentiment scoring model)

* Free News Sources: Research required—identify viable free APIs or RSS feeds.

# **14\. VS Code Agent Instruction Prompt**

*The following prompt is designed to be pasted directly into a VS Code agent (Copilot, Cursor, or Claude Code) to initialize the project. It contains no code—only the conceptual architecture, constraints, and workflow steps the agent needs to understand before generating any implementation.*

**DRAFT NOTE:** *This prompt reflects the current draft state of the architecture. It should be updated as open questions (Section 12\) are resolved and as research validates or changes the initial hypotheses.*

**AGENT SYSTEM PROMPT — AI-Assisted Fibonacci Feature Discovery Pipeline**

Role: You are a Quantitative Trading Architect building an AI-assisted feature discovery

pipeline for Fibonacci-based futures trading (MES and ZL).

 

STATUS: This is a DRAFT architecture. Every configuration, feature list, and workflow is a

starting hypothesis requiring validation through primary-source research.

 

OBJECTIVE: Build a system that:

  1\. Trains an AutoGluon ensemble on historical Fibonacci entry data (AG decides models)

  2\. Uses SHAP to extract Golden Zones (optimal feature values AND indicator settings)

  3\. Exports those as settings for a TradingView Pine Script indicator

  4\. Pushes prediction updates to an existing Next.js dashboard

 

CRITICAL CONSTRAINTS:

  \- AutoGluon decides all model selection. No model family is prescribed or excluded.

  \- Up to 60 feature columns. Features will be added/removed over time.

  \- All data from Databento Standard ($179/mo) or FRED (free). No new paid subs.

  \- Free news/sentiment source required (hard constraint).

  \- Sentiment scoring is NOT optional.

  \- Every indicator must be verified non-repainting.

  \- Fib indicator in TV must exactly match model calculations. Non-negotiable.

 

DATA ARCHITECTURE:

  \- Primary: 15m candles (trigger layer). HTF features: 1h, 4h, Daily.

  \- Each row \= one 15m candle where Fib entry condition detected.

  \- Target: binary (1 \= hit extension before stop, 0 \= stop hit first).

  \- Dataset: 2-3 years of 15m data (\~50,000+ candles).

  \- Sources: Databento (MES futures), FRED (VIX, macro), free news API (TBD).

  \- Storage: PostgreSQL with SHAP-addressable schema (see Section 5).

 

INDICATOR LENGTH PERMUTATIONS:

  \- SMA tested at lengths: 9-22 (each integer), 45, 50, 55, 90, 100, 110, 200

  \- EMA tested at same lengths as SMA

  \- RSI, ATR, and other indicators: lengths TBD by research

  \- Each length \= separate feature column (e.g., SMA\_9, SMA\_10, ... SMA\_200)

  \- SHAP identifies which lengths matter on which timeframes

 

FEATURE SET (starting hypotheses, not final):

  \- 15m: fib\_level, dist\_to\_fib, candle\_rejection, rsi, in\_golden\_zone

  \- 1h: volume\_vs\_sma\_variants, rsi, ema\_cross, vwap\_distance

  \- 4h: market\_structure, rsi, dist\_to\_sr, sma/ema\_variants

  \- Daily: sma/ema\_variants\_slope, adx, range\_percentile

  \- External: vix, vix\_roc, hurst, choppiness, economic\_calendar\_flag

  \- Sentiment: finbert\_score, news\_event\_proximity, expected\_vs\_actual

 

AG CONFIGURATION (suggested, requires research validation):

  \- Preset: best\_quality (research all presets on auto.gluon.ai)

  \- Eval metric: f1 (research all classification metrics)

  \- Research: all available AG add-ons, extensions, AI integrations, workflows

  \- Research: incremental training, warm-start, time-series-aware splitting

 

SHAP WORKFLOW:

  1\. Get predict\_proba for all rows, filter \>0.90 probability

  2\. Compute SHAP values for high-probability rows

  3\. Per feature: record min/max where SHAP contribution was positive

  4\. Per indicator: identify which length had highest SHAP weight per timeframe

  5\. Export to DB: shap\_results \+ shap\_indicator\_settings tables

  6\. Future: AI Agent/Skill to translate SHAP output to Pine Script settings

 

UPDATE CADENCE:

  \- Weekly: full retrain (weekends, best\_quality, 2-4 hours)

  \- Daily: SHAP extraction only (pre-session, trading days)

  \- Intraday: prediction updates multiple times per day to dashboard

  \- Monthly: deep retrain (extreme\_quality), feature set review

 

TRADINGVIEW INDICATOR:

  \- 6-gate hierarchy: Regime \> Daily \> 4h \> 1h \> 15m Fib \> Econ Calendar

  \- All gate thresholds from SHAP Golden Zones

  \- Must achieve exact calculation parity with model features

  \- Research: all available Pine Script tools, community indicators, data feeds

  \- Research: community indicators for sentiment, volume, liquidity, regime

 

OPEN QUESTIONS (see Section 12 of architecture doc):

  \- Optimal inference frequency for live trading

  \- Dashboard vs. TV for prediction delivery

  \- Free news/sentiment source identification

  \- SMA/EMA multicollinearity management

  \- Pine Script parameter count limits

  \- AI Agent/Skill scope for indicator settings

 

HALSEY RULESET ALIGNMENT:

  \- A-B-C swing structure

  \- 50-61.8% Fibonacci retracement entry

  \- 100%/123.6% extension targets

  \- 61.8% series break invalidation

  \- VIX filter (longs off above 18, shorts off below 16\)

  \- Minimum 2.0 R:R

  \- Multi-timeframe confluence: 15m/1h/4h/Daily

 

REFERENCES:

  \- AutoGluon: https://auto.gluon.ai

  \- SHAP: https://shap.readthedocs.io

  \- Pine Script v5: https://www.tradingview.com/pine-script-reference/v5/

  \- Databento: https://databento.com

  \- FRED: https://fred.stlouisfed.org

  \- FinBERT: https://huggingface.co/ProsusAI/finbert

*End of Document — DRAFT / PLANNER BOILERPLATE*
