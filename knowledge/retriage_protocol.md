# Waiting-Room Re-Triage Protocol (site configuration)

This file is the site's configurable protocol. The values are example defaults that each department's clinical governance group must review and set.
PulseQueue supports decisions. It does not replace a triage nurse's judgement.

## Dynamic risk score
Risk = urgency x 10 + growth rate(ESI) x minutes waited + vital-sign trend bonus.
Higher-acuity patients deteriorate faster per untreated minute, so their growth rate is higher.
A patient whose risk crosses 70 is flagged for re-triage, whatever their static rank.

## Vital-sign red flags
Any red flag triggers immediate re-triage regardless of score.
Example defaults: oxygen saturation below 92%, systolic blood pressure below 90 mmHg, heart rate above 130 per minute,
respiratory rate above 30 per minute, temperature above 39.5 C.

## Worsening trend between readings
Comparing the latest set of vitals with the previous one: heart rate up by 20 or more, systolic pressure down by 20 or more,
or oxygen saturation down by 3 points or more each add 15 to the risk score.
A worsening trend matters even when each single reading is still inside the normal range.

## Accelerating risk
If a patient's risk has risen faster over the last 30 minutes than their ESI growth rate predicts (because of vitals), mark them as accelerating.
Accelerating patients are shown first among the flagged patients.

## Silent risers
Patients the dynamic queue ranks in the top slots but the static acuity-only queue does not.
These are the patients the clock is quietly endangering. Review them at the next huddle at the latest.

## Department load
When more than 15 patients are waiting, or arrivals in the last hour exceed 12, re-check the waiting room every 15 minutes instead of every 30.

## Learning and governance
Growth rates are learned from re-triage outcomes (was the flagged patient actually upgraded?) and from misses (upgraded without being flagged).
Changes are proposed with evidence and applied only after approval by the clinical lead.
