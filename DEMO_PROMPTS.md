# WaterLine demo prompts

Active Qdrant collection: `water_knowledge`. It contains synthetic registry documents,
dated observations, and maintenance/safety/repair-visit notices. PostgreSQL still supplies
current registered-asset statuses; switching Qdrant collections does not reset those statuses.

Open `/demo`, keep the infrastructure dashboard beside it, and say the full asset name and
village each turn. Run the first story in order. Reports intentionally change demo data;
questions alone should not create reports. In voice settings, change the demo resident
between turns (end the voice session first).

## The main story: one report helps the next resident

Prepare this story with `python seed_showcase.py`. It appends six unverified synthetic
observations and six notices without deleting history. The clinic and school start operational,
the market has low flow, and the riverside point is under repair. The clinic also has older
failure/repair observations and a scheduled maintenance notice that does not confirm completion.
Retrying the same seed is idempotent. To rehearse again after changing statuses, use a new ID:
`python seed_showcase.py --run-id rehearsal-2`.

1. **Resident A — failure plus alternatives**

   "The Alero clinic hand pump is broken right now. Which other water point in Alero is reported working?"

   Expect BOTH intent. The clinic report commits before answering, the dashboard shows broken,
   and the school borehole is the operational alternative. Expect a change animation on the next
   dashboard poll (about three seconds). Answers need dates and unverified labels.

2. **Resident B — information propagates**

   "Is the Alero clinic hand pump working? Does the repair notice confirm it was fixed?"

   Expect a query only, using Resident A's newly recorded broken status. The retrieved maintenance
   notice describes a scheduled visit, not a completed repair. No new report should be saved.

3. **Resident A — repair**

   "I just used the Alero clinic hand pump and it is working again now. Which water points in Alero are reported working?"

   Expect a new operational observation, a dashboard change animation, retained broken-report history,
   and an unverified answer naming the clinic and school as reported operational.
   Recent disagreement should be explained; operation must not become a drinking-water guarantee.

4. **Historical information arrives late**

   "The Alero clinic hand pump was broken last week."

   Expect the report to be saved without replacing the newer operational observation.
   If the event time is ambiguous, the assistant can ask when it was observed.

## Document retrieval and edge cases

| Scenario | Say this | What to check |
|---|---|---|
| Maintenance notice | "Who should residents contact to report a maintenance problem?" | Retrieve `demo-notice-maintenance`: the fictional village water committee. |
| Historical documents versus current state | "Was the Lumwa school borehole previously reported working, and what is its current reported condition?" | Retrieve dated Qdrant history, then distinguish it from current SQL status. The initial SQL seed says broken; older documents say working. Later demo reports can change this. |
| Scheduled visit versus successful repair | "What does the notice say about the scheduled repair visit in Alero? Does the notice confirm that repairs succeeded?" | Find `demo-notice-visit`. A scheduled visit does not establish repair or operation. |
| Ambiguous asset | "The pipe near the school is broken." | Ask which school/village. Preserve the report without updating an arbitrary asset. |
| Water safety | "The Alero school borehole is reported working. Does that mean its water is safe to drink?" | No safety assurance from operational status. This collection has no verified water-quality tests. |
| Location isolation | "Which water points in Kito are currently reported operational?" | Use Kito SQL records. Do not substitute similarly named assets in Alero or Lumwa. |
| Unknown asset | "Is the Zora Hill spring in fictional Nembi working today?" | Ask for a registered asset/location or explain missing evidence; do not invent an asset. |
| A scheduled repair report | "A repair team is scheduled to visit the Palaro market tap tomorrow." | Save the information without marking the tap operational or treating the visit as completed. |
| General knowledge sharing | "The village water committee accepts fault reports at the community hall on Fridays." Then as Resident B: "When and where does the water committee accept fault reports?" | The new community report should be retrieved as unverified information, without creating a physical asset. |

For the cleanest three-minute pitch, use main-story turns 1–3, then the ambiguous-asset
and water-safety questions. Expand sources to show intent, saved reports, dates, and provenance.
