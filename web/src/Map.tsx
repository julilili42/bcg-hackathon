import { isReport, useEvents, useFocus, useSince } from "./api";
import WaterMap from "./WaterMap";

export default function MapPage() {
  const data = useEvents(2000);
  const focus = useFocus(data);
  const since = useSince(data);
  return <WaterMap waterpoints={data.waterpoints} villages={data.villages} reports={data.events.filter(isReport)} since={since} focus={focus} legend />;
}
