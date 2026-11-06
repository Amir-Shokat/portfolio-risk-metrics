Feature: Weekly Sharpe and Sortino alongside the unchanged daily ratios
  Weekly policy "weekly-ratios-v1": formulas approved; week definition and minimum history not yet approved.

  Scenario: Weekly risk-free return compounds the daily values
    Given a complete week of 5 sessions with a Treasury-bill YTM of 30%
    When the weekly risk-free return is built
    Then it equals (1.30) ** (5 / 250) - 1
    And it is not (1.30) ** (1 / 52) - 1

  Scenario: Daily excess returns are not compounded
    Given a week of portfolio and risk-free returns
    When the weekly excess return is built
    Then it is the weekly portfolio return minus the weekly risk-free return

  Scenario: Positive weekly returns below the weekly risk-free return are shortfalls
    Given weekly returns of 0.1%, 2.0% and -1.0% and a weekly risk-free return of 0.5%
    When weekly downside is calculated
    Then there are 2 shortfalls

  Scenario: Returns equal to the risk-free return give undefined ratios
    Given every weekly return equals the weekly risk-free return
    When weekly ratios are calculated
    Then Sharpe is undefined with "ZERO_EXCESS_SD" and Sortino with "ZERO_RF_DOWNSIDE"

  Scenario: The annualisation factor is not a minimum history
    Given only 5 complete weeks
    When weekly Sharpe is calculated
    Then a diagnostic value exists, scaled by sqrt(52)

  Scenario: Weekly ratios stay unpublished until the week policy is approved
    Given a window with enough data
    When weekly Sharpe and Sortino are assessed
    Then their status is "POLICY_PENDING" and partial edge weeks are reported
