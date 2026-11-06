Feature: Historical risk measures from a supplied daily TWR series
  As the product owner of a retail portfolio page
  I want every risk number to follow one written method and to say clearly when it cannot be shown
  So that users never see a made-up zero, and engineers never have to guess a rule

  Background:
    Given daily returns are decimal simple time-weighted returns (TWR)
    And the risk-free return of a session is (1 + YTM) ** (1 / 250) - 1 for that same session
    And the methodology contract is version "1.3"

  Scenario: Returns are linked rather than added
    Given the daily returns 10% and -10%
    When the cumulative return is calculated
    Then it is -1.00%, not 0%

  Scenario: Opening wealth is included in drawdown
    Given the first return of the window is -10% and the next is +5%
    When the maximum drawdown is calculated
    Then it is -10.00%, measured from the opening wealth point of 1.0

  Scenario: Missing return is not replaced with zero
    Given an official session inside the window has no return row
    When the window is assessed
    Then every offered metric has status "INCOMPLETE_COVERAGE"
    And no value is published and no diagnostic is computed

  Scenario: Genuine zero is retained
    Given a session with a return of exactly 0.0
    When volatility is calculated
    Then that session is counted as a valid observation

  Scenario: Not-computed sessions are excluded and reported
    Given the upstream service marked one session "not_computed"
    When the window is assessed
    Then the session is excluded from the sample and counted under "not computed"
    And the reason "NOT_COMPUTED_SESSIONS_EXCLUDED" is reported without changing the status

  Scenario: Volatility uses sample standard deviation
    Given the daily returns 1% and -1%
    When volatility is calculated with factor 250
    Then it is 0.014142 * sqrt(250) = 22.36%

  Scenario: Downside deviation uses the risk-free target and all observations
    Given the daily returns 0.05%, 0.20%, -0.10% and 0.10%
    And the risk-free return is 0.10% on each of those sessions
    When downside deviation is calculated
    Then there are 2 shortfalls, because +0.05% is below the risk-free return and 0.10% equals it
    And the divisor is 4, all aligned observations, giving a periodic value of 0.10308%

  Scenario: Sharpe uses the standard deviation of excess returns
    Given returns of 1% and 2% and risk-free returns of 0% and 1% on the same sessions
    When the Sharpe ratio is calculated
    Then it is undefined with reason "ZERO_EXCESS_SD", even though the raw returns vary

  Scenario: Zero denominator is undefined, not zero or infinite
    Given a one-year window with 250 observations and no return below the risk-free return
    When Sortino is assessed
    Then its status is "UNDEFINED" and the reason "MIN_SHORTFALLS_NOT_MET" is kept as well

  Scenario: One-month volatility is withheld below its observation gate
    Given a one-month window with 29 valid observations
    When volatility is assessed
    Then its status is "INSUFFICIENT_HISTORY"
    And the computed number is kept only as an internal diagnostic

  Scenario: One-month volatility is shown at its observation gate
    Given a one-month window with 30 valid observations
    When volatility is assessed
    Then its status is "OK" and the value is published

  Scenario: Ratio history has no elapsed-calendar-day gate
    Given 250 valid aligned observations that span fewer than 365 calendar days
    When Sharpe is assessed for the one-year horizon
    Then its status is "OK"

  Scenario: Ratio history needs 250 observations
    Given 249 valid aligned observations
    When Sharpe is assessed for the one-year horizon
    Then its status is "INSUFFICIENT_HISTORY"

  Scenario: Missing risk-free quote blocks only the metrics that read it
    Given one session in the window has no Treasury-bill quote
    When the window is assessed
    Then Sharpe has status "RF_MISSING"
    And volatility, which does not read the risk-free series, is still "OK"

  Scenario: Total loss is a pending policy, not an invalid number
    Given a session with a return of exactly -100%
    When the window is assessed
    Then the status is "POLICY_PENDING"
    And a return below -100% would be "INVALID_INPUT" instead

  Scenario: A return on a closed day is invalid
    Given a return row dated on a day the official calendar marks as closed
    When the window is assessed
    Then the status is "INVALID_INPUT"

  Scenario: Metrics not offered for a horizon say so
    Given a one-month window
    When Sharpe is assessed
    Then its status is "NOT_OFFERED", which is a product rule and not a calculation failure
