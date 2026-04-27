/**
 * HARNESS SELF-SEEDED VIOLATION · Rule D4 (legacy-301-full-coverage)
 *
 * PURPOSE: proves D4 catches a legacy redirect missing from an App-like file.
 * This fixture intentionally OMITS the legacy dashboard redirect so D4 must
 * emit at least one "Legacy redirect missing" violation.
 *
 * DO NOT IMPORT. See A1_cjk_leak.cifixture.jsx for fixture policy.
 * The dashboard redirect is deliberately absent — do NOT add it back.
 */

/* eslint-disable */
import React from 'react';

export function D4_MissingRedirectApp() {
  return (
    <Routes>
      <Route path="/topics"                            from="/topics" />
      <Route path="/industry"                          from="/industry" />
      <Route path="/industries"                        from="/industries" />
      <Route path="/industries/:id"                    from="/industries/:id" />
      <Route path="/knowledge-graph"                   from="/knowledge-graph" />
      <Route path="/diagnostics"                       from="/diagnostics" />
      <Route path="/reports"                           from="/reports" />
      <Route path="/brands/:id"                        from="/brands/:id" />
      <Route path="/brands/:id/simulator"              from="/brands/:id/simulator" />
      <Route path="/brands/:id/products/:productId"    from="/brands/:id/products/:productId" />
    </Routes>
  );
}

const Route = () => null;
const Routes = ({ children }) => null;
