/**
 * Canonical TypeScript insert payload types for the MES 15m fib candidate contract.
 *
 * Mirrors the DDL from migration 037 (warbird_canonical_warbird_tables).
 * No runtime logic. No validators. No writer functions.
 * These are application-side insert payloads only — DB-generated identity and
 * server-managed timestamp columns (uuid PKs, created_at, emitted_at) are omitted.
 *
 * Do not use:
 *   - GO, NO_GO, EXPIRED, NO_REACTION
 *   - prob_hit_*, hit_*_first
 *   - collapsed STOPPED state (use STOPPED_PRE_TP1 or STOPPED_POST_TP1)
 *   - types from lib/warbird/types.ts
 */

// ============================================================
// Literal union types mirroring migration 037 enums
// ============================================================

/** MES 15m is the sole canonical contract timeframe. */
export type CanonicalTimeframe = "M15";

/** MES E-mini S&P 500 is the sole canonical symbol. */
export type CanonicalSymbolCode = "MES";

/** Trade direction for a fib setup. */
export type CanonicalDirection = "LONG" | "SHORT";

/**
 * Policy decision vocabulary. These are entry-gate outputs, not realized outcomes.
 * TAKE_TRADE = packet approved; WAIT = hold for more structure; PASS = no valid candidate.
 */
export type CanonicalDecisionCode = "TAKE_TRADE" | "WAIT" | "PASS";

/**
 * Realized outcome codes for a scored fib candidate.
 * EXPIRED and NO_REACTION are prohibited — unresolved rows are CENSORED.
 * The pre/post distinction on STOPPED encodes where in the trade leg the stop fired.
 */
export type CanonicalOutcomeCode =
  | "TP2_HIT"
  | "STOPPED_PRE_TP1"
  | "STOPPED_POST_TP1"
  | "CENSORED_PRE_TP1"
  | "CENSORED_POST_TP1";

/** Live signal tracking status for warbird_signals_15m. */
export type CanonicalSignalStatus =
  | "ACTIVE"
  | "TP1_HIT"
  | "TP2_HIT"
  | "STOPPED"
  | "CANCELLED";

/** Structural archetype for the fib candidate entry pattern. */
export type CanonicalSetupArchetype =
  | "ACCEPT_CONTINUATION"
  | "ZONE_REJECTION"
  | "PIVOT_CONTINUATION"
  | "FAILED_MOVE_REVERSAL"
  | "REENTRY_AFTER_TP1";

/** Stop placement family for the candidate. */
export type CanonicalStopFamily =
  | "FIB_INVALIDATION"
  | "FIB_ATR"
  | "STRUCTURE"
  | "FIXED_ATR";

/** Named fib level touched at candidate entry. */
export type CanonicalFibLevel =
  | "ZERO"
  | "FIB_236"
  | "FIB_382"
  | "FIB_500"
  | "FIB_618"
  | "FIB_786"
  | "ONE"
  | "TP1"
  | "TP2";

/** Macro regime bucket at the time of candidate generation. */
export type CanonicalRegimeBucket = "RISK_ON" | "NEUTRAL" | "RISK_OFF" | "CONFLICT";

/** CME session bucket at bar close. */
export type CanonicalSessionBucket =
  | "RTH_OPEN"
  | "RTH_CORE"
  | "LUNCH"
  | "RTH_PM"
  | "ETH";

// ============================================================
// FibSnapshotInsert
// Insert payload for warbird_fib_engine_snapshots_15m.
// One row per (symbol_code, timeframe, bar_close_ts, fib_engine_version).
// ============================================================

/**
 * All fields the application must supply when writing a fib engine snapshot.
 * Omitted: snapshot_id (gen_random_uuid), created_at (now()).
 *
 * Fields currently absent from buildFibGeometry output and required before
 * any writer can produce valid snapshot rows:
 *   anchor_hash, fib_engine_version, resolved_left_bars, resolved_right_bars,
 *   resolved_anchor_lookback_bars, resolved_anchor_spacing_bars,
 *   reversal_mode_code, anchor_lock_state_code, exhaustion_precursor_flag,
 *   exhaustion_precursor_score, exhaustion_location_code
 */
export type FibSnapshotInsert = {
  bar_close_ts: string;
  timeframe: CanonicalTimeframe;
  symbol_code: CanonicalSymbolCode;

  /** Semver string identifying the fib engine build (e.g. "1.0.0"). */
  fib_engine_version: string;

  direction: CanonicalDirection;

  /**
   * Deterministic content hash of the anchor pivot pair.
   * Enables deduplication and lineage tracking across snapshots.
   */
  anchor_hash: string;

  anchor_high: number;
  anchor_low: number;
  anchor_high_ts: string;
  anchor_low_ts: string;

  /** Absolute point distance of the fib anchor range (must be > 0). */
  anchor_range_pts: number;

  /** Resolved pivot lookback bars used for left pivot detection (must be > 0). */
  resolved_left_bars: number;
  /** Resolved pivot lookback bars used for right pivot detection (must be > 0). */
  resolved_right_bars: number;
  /** Resolved anchor lookback window in bars (must be > 0). */
  resolved_anchor_lookback_bars: number;
  /** Resolved minimum spacing between anchor pivots in bars (must be >= 0). */
  resolved_anchor_spacing_bars: number;

  /** Engine reversal detection mode at snapshot time (e.g. "STANDARD", "AGGRESSIVE"). */
  reversal_mode_code: string;
  /** Anchor lock state at snapshot time (e.g. "LOCKED", "UNLOCKED", "PROVISIONAL"). */
  anchor_lock_state_code: string;

  // Fib price levels computed from the anchor pair.
  fib_zero: number;
  fib_236: number;
  fib_382: number;
  fib_500: number;
  fib_618: number;
  fib_786: number;
  fib_one: number;
  fib_tp1: number;
  fib_tp2: number;

  /**
   * True when abs(fib_tp1 - fib_one) >= 20 points, i.e. the minimum viable
   * trade distance is met. The candidates table further enforces this per-candidate.
   */
  target_eligible_20pt: boolean;

  /** True when the engine detected an exhaustion precursor pattern at this bar. */
  exhaustion_precursor_flag: boolean;

  /** Numeric score [0,1] for the exhaustion precursor, null when flag is false. */
  exhaustion_precursor_score: number | null;

  /**
   * Location code for where the exhaustion precursor fired
   * (e.g. "FIB_618", "FIB_786"), null when flag is false.
   */
  exhaustion_location_code: string | null;
};

// ============================================================
// FibCandidateInsert
// Insert payload for warbird_fib_candidates_15m.
// Modeled as a discriminated union on packet_id nullability to
// mirror the DDL ck_warbird_fib_candidates_scored_state constraint:
//   unscored: ALL of {packet_id, decision_code, tp1_probability,
//             tp2_probability, reversal_risk, expected_mae_pts,
//             expected_mfe_pts} must be NULL.
//   scored:   ALL of the above must be NOT NULL.
// ============================================================

type FibCandidateInsertBase = {
  snapshot_id: string;
  bar_close_ts: string;
  timeframe: CanonicalTimeframe;
  symbol_code: CanonicalSymbolCode;

  /**
   * Sequence number within the bar (>= 1). Default 1 for the primary candidate;
   * increment for additional candidates derived from the same snapshot.
   */
  candidate_seq: number;

  direction: CanonicalDirection;
  setup_archetype: CanonicalSetupArchetype;
  fib_level_touched: CanonicalFibLevel;

  /** Numeric ratio of the fib level (e.g. 0.618). */
  fib_ratio_touched: number;

  entry_price: number;
  stop_loss: number;
  tp1_price: number;
  tp2_price: number;

  stop_family: CanonicalStopFamily;

  /**
   * Must always be true — the ck_warbird_fib_candidates_target_eligible
   * constraint rejects false. Typed as literal to prevent drift.
   */
  target_eligible_20pt: true;

  /** Event mode code at candidate generation (e.g. "BREAKOUT", "RETEST"). */
  event_mode_code: string;
  /** Pivot interaction code (e.g. "ABOVE_PIVOT", "AT_PIVOT", "BELOW_PIVOT"). */
  pivot_interaction_code: string;

  regime_bucket: CanonicalRegimeBucket;
  session_bucket: CanonicalSessionBucket;

  /** Pre-scoring confidence [0, 100]. */
  confidence_score: number;

  /**
   * Optional human-readable reason code for the decision.
   * Nullable text in the DDL — not part of the scored-state all-or-nothing check.
   */
  decision_reason_code: string | null;
};

/** Candidate written before AG scoring. No packet, no probabilities. */
type UnscoredFibCandidateInsert = FibCandidateInsertBase & {
  packet_id: null;
  decision_code: null;
  tp1_probability: null;
  tp2_probability: null;
  reversal_risk: null;
  expected_mae_pts: null;
  expected_mfe_pts: null;
};

/** Candidate after AG scoring. All probability fields are required. */
type ScoredFibCandidateInsert = FibCandidateInsertBase & {
  packet_id: string;
  decision_code: CanonicalDecisionCode;
  tp1_probability: number;
  tp2_probability: number;
  reversal_risk: number;
  expected_mae_pts: number;
  expected_mfe_pts: number;
};

/**
 * Insert payload for warbird_fib_candidates_15m.
 * The DDL all-or-nothing constraint on scoring fields is enforced here:
 * you must supply either all scored fields or none of them.
 */
export type FibCandidateInsert = UnscoredFibCandidateInsert | ScoredFibCandidateInsert;

// ============================================================
// CandidateOutcomeInsert
// Insert payload for warbird_candidate_outcomes_15m.
// Modeled as a discriminated union on outcome_code to mirror the
// DDL ck_warbird_outcomes_code_mapping constraint, which requires
// an exact correspondence between outcome_code and the boolean flags.
// Each variant types the booleans as literals so the compiler enforces
// the same invariant the DB constraint does.
// ============================================================

type CandidateOutcomeInsertBase = {
  candidate_id: string;
  bar_close_ts: string;
  symbol_code: CanonicalSymbolCode;
  timeframe: CanonicalTimeframe;

  /** Maximum adverse excursion in points (>= 0). */
  mae_pts: number;
  /** Maximum favorable excursion in points (>= 0). */
  mfe_pts: number;

  /** Semver string identifying the scorer build that resolved this outcome. */
  scorer_version: string;
  scored_at: string;
};

/**
 * Encodes the DDL reversal invariant:
 *   reversal_detected = true  => reversal_ts must be non-null (ck_warbird_outcomes_reversal_ts)
 *   reversal_detected = false => reversal_ts must be null
 */
type ReversalDetected = { reversal_detected: true; reversal_ts: string };
type ReversalNotDetected = { reversal_detected: false; reversal_ts: null };
type ReversalState = ReversalDetected | ReversalNotDetected;

/**
 * TP1 and TP2 both hit before stop.
 * tp1_hit_ts and tp2_hit_ts are required.
 */
type Tp2HitOutcomeInsert = CandidateOutcomeInsertBase & ReversalState & {
  outcome_code: "TP2_HIT";
  tp1_before_sl: true;
  tp2_before_sl: true;
  sl_before_tp1: false;
  sl_after_tp1_before_tp2: false;
  is_censored: false;
  tp1_hit_ts: string;
  tp2_hit_ts: string;
  stopped_ts: null;
  censored_at_ts: null;
};

/**
 * Stop hit before TP1 was reached.
 * stopped_ts is required.
 */
type StoppedPreTp1OutcomeInsert = CandidateOutcomeInsertBase & ReversalState & {
  outcome_code: "STOPPED_PRE_TP1";
  sl_before_tp1: true;
  tp1_before_sl: false;
  tp2_before_sl: false;
  sl_after_tp1_before_tp2: false;
  is_censored: false;
  stopped_ts: string;
  tp1_hit_ts: null;
  tp2_hit_ts: null;
  censored_at_ts: null;
};

/**
 * TP1 was hit, then stop hit before TP2.
 * Both tp1_hit_ts and stopped_ts are required.
 * The DDL enforces stopped_ts >= tp1_hit_ts.
 */
type StoppedPostTp1OutcomeInsert = CandidateOutcomeInsertBase & ReversalState & {
  outcome_code: "STOPPED_POST_TP1";
  tp1_before_sl: true;
  sl_after_tp1_before_tp2: true;
  tp2_before_sl: false;
  sl_before_tp1: false;
  is_censored: false;
  tp1_hit_ts: string;
  stopped_ts: string;
  tp2_hit_ts: null;
  censored_at_ts: null;
};

/**
 * Observation window closed before TP1 or stop was reached.
 * Not a failure — row is censored for training purposes.
 * censored_at_ts is required.
 */
type CensoredPreTp1OutcomeInsert = CandidateOutcomeInsertBase & ReversalState & {
  outcome_code: "CENSORED_PRE_TP1";
  is_censored: true;
  tp1_before_sl: false;
  tp2_before_sl: false;
  sl_before_tp1: false;
  sl_after_tp1_before_tp2: false;
  censored_at_ts: string;
  tp1_hit_ts: null;
  tp2_hit_ts: null;
  stopped_ts: null;
};

/**
 * TP1 was hit, then observation window closed before TP2 or second stop.
 * Both tp1_hit_ts and censored_at_ts are required.
 * The DDL enforces censored_at_ts >= tp1_hit_ts.
 */
type CensoredPostTp1OutcomeInsert = CandidateOutcomeInsertBase & ReversalState & {
  outcome_code: "CENSORED_POST_TP1";
  is_censored: true;
  tp1_before_sl: true;
  tp2_before_sl: false;
  sl_before_tp1: false;
  sl_after_tp1_before_tp2: false;
  tp1_hit_ts: string;
  censored_at_ts: string;
  tp2_hit_ts: null;
  stopped_ts: null;
};

/**
 * Insert payload for warbird_candidate_outcomes_15m.
 * Discriminated on outcome_code. Boolean flags are typed as literals per variant
 * to mirror the ck_warbird_outcomes_code_mapping DDL constraint at compile time.
 */
export type CandidateOutcomeInsert =
  | Tp2HitOutcomeInsert
  | StoppedPreTp1OutcomeInsert
  | StoppedPostTp1OutcomeInsert
  | CensoredPreTp1OutcomeInsert
  | CensoredPostTp1OutcomeInsert;

// ============================================================
// SignalInsert
// Insert payload for warbird_signals_15m.
// Only candidates with decision_code = TAKE_TRADE produce a signal row.
// ============================================================

/**
 * Insert payload for warbird_signals_15m.
 * Omitted: signal_id (gen_random_uuid), emitted_at (now()), created_at (now()).
 *
 * decision_code is typed as the literal 'TAKE_TRADE' — the DDL
 * ck_warbird_signals_decision_code constraint rejects all other values,
 * and the fk_warbird_signals_take_trade foreign key enforces the same
 * invariant on the candidate row.
 */
export type SignalInsert = {
  candidate_id: string;

  /** Locked to TAKE_TRADE by DDL constraint. No other value is permitted. */
  decision_code: "TAKE_TRADE";

  bar_close_ts: string;
  timeframe: CanonicalTimeframe;
  symbol_code: CanonicalSymbolCode;
  direction: CanonicalDirection;

  /**
   * Initial signal status on insert. Defaults to ACTIVE in the DB;
   * application must supply it explicitly per the type contract.
   */
  status: CanonicalSignalStatus;

  entry_price: number;
  stop_loss: number;
  tp1_price: number;
  tp2_price: number;

  /** Required — signals must reference a promoted packet. */
  packet_id: string;

  /** Whether a TradingView alert payload has been prepared for this signal. */
  tv_alert_ready: boolean;
};
