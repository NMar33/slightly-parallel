# How to look when writing a test

Cases from this repository where a test missed a bug, or a bug was found
only after the way of looking changed. Each case ends with the question
that would have found it. Add a case only when a test taught something
not already here. Round 4 of the audit (docs/audit/rounds/2611-10.md)
holds the details.

## 1. Make a flaky test show what it saw

The terminal test on macOS failed in some runs. A longer wait changed
nothing. The cause was found only after the test printed the pane on
failure: it counted rows in the joined text, and the CI machine's random
host name was sometimes long enough to wrap the command onto a second
row. The varying input was the host name, not the timing.

Question: what did the test see at the moment it failed?

## 2. A skip hides code that was never tested

17 tests were skipped on Windows because Python has no `tzset` there. The
CI machines run in UTC anyway. When the tests ran there, they found a real
bug at once: the drive letter changed the key of the Codex account.

Question: under what condition can this test run after all?

## 3. A green test can check nothing

The Real Codex job passed on all three systems. Codex answered "not
signed in" on each: the job checked only that the program started and
ended.

Question: what did the green test actually print?

## 4. Do the parts add up to the whole, on real data?

The unit test of the usage split passed: it built its input by hand. On
the operator's data the parts of the bar added up to 443% of a total of
402%: Codex's replies were counted in Claude Code's limit.

Question: does the whole equal the sum of its parts on real data?

## 5. A real agent's failure is a product bug until shown otherwise

Claude Code sent a task's tags as a list. The server refused `ag_followup`
and listed `ag_followup` among the allowed tags in the same message. The
paid runs with real agents showed this twice; both times it was read as
the agent's mistake.

Question: does the error message contradict itself?

## 6. A failed later step must not erase the steps that worked

Reading Codex's limits lost the limits already read when the next request
hung. A corrupt feed file was read as empty and written back, and the pins
were lost.

Question: what happens to what already worked if the next step fails?

## 7. Two "now"s in one test are a boundary

Two notes were posted on either side of a minute change. Another test took
0 on the monotonic clock as "more than a minute ago"; on a machine started
less than a minute earlier it was not.

Question: what if a minute, a day or the time zone changes between the
two "now"s?

## Questions before writing a test

1. What did the test see at the moment it failed?
2. Under what condition can this test run after all?
3. What did the green test actually print?
4. Does the whole equal the sum of its parts on real data?
5. Does the error message contradict itself?
6. What happens to what already worked if the next step fails?
7. What if a minute, a day or the time zone changes between two "now"s?
