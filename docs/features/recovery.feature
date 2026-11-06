Feature: Recovery of the maximum drawdown, counted in official market sessions
  Recovery policy "1.1-window-bound-session-count".

  Scenario: Exclude the trough session and include the recovery session
    Given the trough is on a Saturday and the first return to the peak is on the following Monday
    And Sunday is an official session
    When the recovery duration is counted
    Then it is 2 sessions

  Scenario: Market closures do not increase recovery duration
    Given the trough is on a Saturday and the recovery is on the following Monday
    And Sunday is an official holiday
    When the recovery duration is counted
    Then it is 1 session

  Scenario: Recovery is searched only inside the selected window
    Given a drawdown whose recovery happens after the end of a past window
    When that past window is assessed
    Then the status is "NOT_RECOVERED" with the label "not recovered by the end of this period"
    And assessing a later window that contains the recovery gives a number of sessions

  Scenario: No drawdown is not a zero-session recovery
    Given a window in which wealth never falls below its running peak
    When recovery is assessed
    Then the status is "NO_DRAWDOWN" and no number is shown

  Scenario: Missing coverage is not an observed recovery duration
    Given an official session inside the window has no return row
    When recovery is assessed
    Then the status is "INCOMPLETE_COVERAGE", not "NOT_RECOVERED"
