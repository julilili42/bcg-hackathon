# Water points, Kisarawe district (Pwani, Tanzania)

`kisarawe.json` is a snapshot of the Water Point Data Exchange basic dataset (`eqje-vguj`,
https://data.waterpointdata.org) filtered to `clean_country_name='Tanzania' AND clean_adm2='Kisarawe'
AND is_latest=true`, fetched 2026-10-16: 330 points, surveys from 2008 to 2009.

Imported as the `water` domain baseline by `reach.ingest.wpdx`. `make seed LIVE=1` refetches from the
API instead of using this file. WPDx points have no human names; `reach.ingest.wpdx` generates
`<ward> <source type> <n>` names and `data/demo/aliases.csv` adds memorable aliases for the demo.
