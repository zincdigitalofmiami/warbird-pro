-- Restrict news_signals materialized view to authenticated users only.
-- Migration 028 dropped the RLS-protected news_signals table and recreated
-- it as a materialized view. Materialized views cannot have RLS in Postgres,
-- so we use GRANT to restrict SELECT access explicitly.
--
-- Source tables (econ_news_article_assessments, geopolitical_risk_1d,
-- trump_effect_1d) retain their own RLS policies. This GRANT adds an
-- explicit boundary on the aggregated view itself.
revoke all on news_signals from anon, public;
grant select on news_signals to authenticated;
grant select on news_signals to service_role;
