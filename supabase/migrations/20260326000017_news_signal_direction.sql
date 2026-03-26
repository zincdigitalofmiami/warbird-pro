-- Lock news_signals to market-impact polarity instead of trade-direction semantics.

create type market_impact_direction as enum (
  'BULLISH',
  'BEARISH'
);

alter table news_signals
  alter column direction type market_impact_direction
  using (
    case direction::text
      when 'LONG' then 'BULLISH'::market_impact_direction
      when 'SHORT' then 'BEARISH'::market_impact_direction
      else null
    end
  );
