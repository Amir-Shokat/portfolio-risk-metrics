Feature: Versioned methodology and reproducible results

  Scenario: Every report names the methodology and policy versions it used
    When any window is assessed
    Then the report header shows the methodology version, each policy version and a contract fingerprint

  Scenario: A rule change invalidates only the metrics that depend on it
    Given the minimum history of maximum drawdown changes from 20 to 30
    When the change-impact map is computed
    Then only maximum drawdown and recovery are affected
    And cached Sharpe ratios keep their keys

  Scenario: Correction creates a new result dependency
    Given the risk-free series is corrected to a new revision
    When result keys are rebuilt
    Then the Sharpe key changes and the volatility key does not

  Scenario: Published results are superseded, never overwritten
    Given a Sharpe result was published and a corrected one is published later
    Then the slot shows the new result
    And the old result is kept and marked as superseded
    And publishing the same result again stores nothing new
